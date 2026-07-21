from app.analyzer.service import TemplateAnalyzer
from app.core.config import Settings
from app.core.exceptions import FeatureDisabledError
from app.database.session import async_session_factory
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
from app.runtime.settings import RuntimeSettingsService


class ApplicationContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session_factory = async_session_factory
        self.runtime_settings = RuntimeSettingsService(async_session_factory, settings)
        self.operation_service = OperationService(async_session_factory)
        self.operation_runner = OperationRunner(self.operation_service)
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

    async def initialize(self) -> None:
        await self.runtime_settings.initialize()
        await self.reload_runtime()
        await self.operation_runner.initialize()

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

    async def reload_runtime(self) -> None:
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

        # Keep replaced clients alive until shutdown so an operation already in flight is not
        # interrupted by an administrator changing runtime settings.
        self._retired_clients.extend(previous_clients)

    async def close(self) -> None:
        await self.operation_runner.shutdown()
        for client in [*self._async_clients, *self._retired_clients]:
            close = getattr(client, "close", None)
            if close is not None:
                await close()
        self._async_clients.clear()
        self._retired_clients.clear()
