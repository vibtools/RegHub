from app.analyzer.service import TemplateAnalyzer
from app.core.config import Settings
from app.core.exceptions import FeatureDisabledError
from app.database.session import async_session_factory
from app.governance.audit import AuditService
from app.infrastructure.cache import CatalogCacheService
from app.infrastructure.rate_limit import RateLimitService
from app.integrations.bitbucket.client import BitbucketClient
from app.integrations.github.client import GitHubClient
from app.integrations.gitlab.client import GitLabClient
from app.integrations.openai.client import AIMetadataEnricher
from app.integrations.screenshot.client import ScreenshotService
from app.operations.service import OperationRunner, OperationService
from app.registry.adapters.bitbucket import BitbucketRegistryAdapter
from app.registry.adapters.github import GitHubRegistryAdapter
from app.registry.adapters.gitlab import GitLabRegistryAdapter
from app.registry.adapters.registry import AdapterRegistry
from app.registry.media import ScreenshotJobService
from app.registry.template import TemplateImportService, TemplateSyncService
from app.runtime.api_access import ApiAccessService
from app.runtime.settings import RuntimeSettingsService


class ApplicationContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session_factory = async_session_factory
        self.runtime_settings = RuntimeSettingsService(async_session_factory, settings)
        self.api_access = ApiAccessService(
            async_session_factory, settings.session_secret.get_secret_value()
        )
        self.audit = AuditService(async_session_factory, settings.audit_keyring)
        self.catalog_cache = CatalogCacheService(
            backend=settings.cache_backend,
            redis_url=settings.redis_dsn,
            ttl_seconds=settings.catalog_cache_ttl_seconds,
        )
        self.rate_limiter = RateLimitService(
            backend=settings.rate_limit_backend,
            redis_url=settings.redis_dsn,
        )
        self.operation_service = OperationService(async_session_factory)
        self.operation_runner = OperationRunner(
            self.operation_service,
            backend=settings.operation_backend,
            redis_url=settings.redis_dsn,
            queue_name=settings.operation_queue_name,
            lock_ttl_seconds=settings.operation_lock_ttl_seconds,
            poll_seconds=settings.operation_worker_poll_seconds,
        )
        self.operation_runner.bind(self)

        self.github_authenticated = False
        self.gitlab_authenticated = False
        self.bitbucket_authenticated = False
        self.ai_metadata_enabled = False
        self.screenshot_service_enabled = False
        self.local_upload_enabled = settings.local_upload_enabled
        self.local_upload_max_bytes = settings.local_upload_max_bytes
        self.local_upload_max_uncompressed_bytes = settings.local_upload_max_uncompressed_bytes
        self.local_upload_max_entries = settings.local_upload_max_entries
        self.adapter_names: list[str] = []
        self.template_import_service: TemplateImportService
        self.template_sync_service: TemplateSyncService
        self.screenshot_job_service: ScreenshotJobService
        self.screenshot_service = ScreenshotService(url=None, token=None)
        self._async_clients: list[object] = []
        self._retired_clients: list[object] = []

    async def initialize(self, *, worker_process: bool = False) -> None:
        await self.runtime_settings.initialize()
        await self.api_access.initialize()
        await self.catalog_cache.initialize()
        await self.rate_limiter.initialize()
        await self.reload_runtime()
        await self.operation_runner.initialize(
            worker_process=worker_process,
            redis_worker_enabled=self.feature_enabled("redis_worker"),
        )

    def feature_enabled(self, key: str, *, task: bool = False) -> bool:
        return self.runtime_settings.feature_enabled(key, task=task)

    def require_feature(self, key: str, *, task: bool = False) -> None:
        if not self.feature_enabled(key, task=task):
            raise FeatureDisabledError(f"Feature '{key}' is disabled in RegHub Settings")

    @staticmethod
    def _integer(value: object, default: int, minimum: int = 3, maximum: int = 120) -> int:
        try:
            parsed = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default
        return max(minimum, min(parsed, maximum))

    async def apply_runtime_infrastructure(self, *, verify_redis_worker: bool = False) -> None:
        """Apply runtime infrastructure switches without rebuilding the application.

        Redis itself and the standalone worker remain deployment infrastructure. Once
        they are provisioned, the Settings feature flag can safely move new operations
        between the web process and the durable queue without a web redeploy.
        """
        await self.operation_runner.set_redis_worker_enabled(
            self.feature_enabled("redis_worker"),
            verify_worker=verify_redis_worker,
        )

    async def reload_runtime(self, *, preserve_inflight: bool = True) -> None:
        await self.runtime_settings.reload()
        previous_clients = self._async_clients

        github = self.runtime_settings.integration("github")
        gitlab = self.runtime_settings.integration("gitlab")
        bitbucket = self.runtime_settings.integration("bitbucket")
        ai = self.runtime_settings.integration("ai")
        screenshot = self.runtime_settings.integration("screenshot")

        github_client = GitHubClient(
            token=github.secret,
            timeout=self._integer(
                (github.config or {}).get("timeout"), self.settings.github_timeout_seconds
            ),
            allow_private=bool(
                (github.config or {}).get(
                    "allow_private", self.settings.github_allow_private_repositories
                )
            ),
        )
        gitlab_client = GitLabClient(
            token=gitlab.secret,
            timeout=self._integer(
                (gitlab.config or {}).get("timeout"), self.settings.provider_timeout_seconds
            ),
        )
        bitbucket_client = BitbucketClient(
            username=bitbucket.username,
            app_password=bitbucket.secret,
            timeout=self._integer(
                (bitbucket.config or {}).get("timeout"), self.settings.provider_timeout_seconds
            ),
        )

        adapters = []
        if github.enabled and self.feature_enabled("github_import"):
            adapters.append(GitHubRegistryAdapter(github_client))
        if gitlab.enabled and self.feature_enabled("gitlab_import"):
            adapters.append(GitLabRegistryAdapter(gitlab_client))
        if bitbucket.enabled and self.feature_enabled("bitbucket_import"):
            adapters.append(BitbucketRegistryAdapter(bitbucket_client))
        adapter_registry = AdapterRegistry(adapters)

        ai_feature_enabled = self.feature_enabled("ai_metadata") and ai.enabled
        ai_enricher = AIMetadataEnricher(
            enabled=ai_feature_enabled,
            base_url=ai.base_url,
            api_key=ai.secret,
            model=str((ai.config or {}).get("model") or self.settings.ai_model),
            timeout=self._integer(
                (ai.config or {}).get("timeout"), self.settings.provider_timeout_seconds
            ),
        )
        screenshot_feature_enabled = (
            self.feature_enabled("screenshot_generation") and screenshot.enabled
        )
        self.screenshot_service = ScreenshotService(
            url=screenshot.base_url if screenshot_feature_enabled else None,
            token=screenshot.secret,
            timeout=self._integer((screenshot.config or {}).get("timeout"), 45, maximum=180),
        )
        analyzer = TemplateAnalyzer()
        provider_auto_create = self.feature_enabled("provider_auto_create", task=True)
        self.template_import_service = TemplateImportService(
            async_session_factory,
            adapter_registry,
            analyzer,
            ai_enricher,
            self.screenshot_service,
            provider_auto_create_enabled=provider_auto_create,
        )
        self.template_sync_service = TemplateSyncService(
            async_session_factory,
            adapter_registry,
            analyzer,
            ai_enricher,
            self.screenshot_service,
            provider_auto_create_enabled=provider_auto_create,
        )
        self.screenshot_job_service = ScreenshotJobService(
            async_session_factory, self.screenshot_service
        )

        self.github_authenticated = github_client.is_authenticated
        self.gitlab_authenticated = gitlab_client.is_authenticated
        self.bitbucket_authenticated = bitbucket_client.is_authenticated
        self.ai_metadata_enabled = ai_enricher.enabled
        self.screenshot_service_enabled = self.screenshot_service.enabled
        self.local_upload_enabled = self.feature_enabled("local_import", task=True)
        self.adapter_names = adapter_registry.names
        self._async_clients = [gitlab_client, bitbucket_client]
        await self.catalog_cache.invalidate_all()

        if preserve_inflight:
            # The web process may be serving an operation while an administrator changes Settings.
            # Keep replaced clients alive until shutdown so that in-flight work is not interrupted.
            self._retired_clients.extend(previous_clients)
        else:
            # A standalone worker reloads Settings only at an operation boundary, where no previous
            # provider client is still in use. Close superseded async clients immediately to avoid
            # an unbounded retired-client list during long-lived worker operation.
            for client in previous_clients:
                close = getattr(client, "close", None)
                if close is not None:
                    await close()

    async def close(self) -> None:
        await self.operation_runner.shutdown()
        await self.catalog_cache.close()
        await self.rate_limiter.close()
        for client in [*self._async_clients, *self._retired_clients]:
            close = getattr(client, "close", None)
            if close is not None:
                await close()
        self._async_clients.clear()
        self._retired_clients.clear()
