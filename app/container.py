from app.analyzer.service import TemplateAnalyzer
from app.core.config import Settings
from app.database.session import async_session_factory
from app.integrations.bitbucket.client import BitbucketClient
from app.integrations.github.client import GitHubClient
from app.integrations.gitlab.client import GitLabClient
from app.integrations.openai.client import AIMetadataEnricher
from app.integrations.screenshot.client import ScreenshotService
from app.registry.adapters.bitbucket import BitbucketRegistryAdapter
from app.registry.adapters.github import GitHubRegistryAdapter
from app.registry.adapters.gitlab import GitLabRegistryAdapter
from app.registry.adapters.registry import AdapterRegistry
from app.registry.template import TemplateImportService, TemplateSyncService


class ApplicationContainer:
    def __init__(self, settings: Settings) -> None:
        github_client = GitHubClient(
            token=settings.github_token.get_secret_value() if settings.github_token else None,
            timeout=settings.github_timeout_seconds,
            allow_private=settings.github_allow_private_repositories,
        )
        gitlab_client = GitLabClient(
            token=settings.gitlab_token.get_secret_value() if settings.gitlab_token else None,
            timeout=settings.provider_timeout_seconds,
        )
        bitbucket_client = BitbucketClient(
            username=settings.bitbucket_username,
            app_password=(
                settings.bitbucket_app_password.get_secret_value()
                if settings.bitbucket_app_password
                else None
            ),
            timeout=settings.provider_timeout_seconds,
        )
        adapters = AdapterRegistry(
            [
                GitHubRegistryAdapter(github_client),
                GitLabRegistryAdapter(gitlab_client),
                BitbucketRegistryAdapter(bitbucket_client),
            ]
        )
        analyzer = TemplateAnalyzer()
        ai_enricher = AIMetadataEnricher(
            enabled=settings.ai_metadata_enabled,
            base_url=str(settings.ai_base_url).rstrip("/") if settings.ai_base_url else None,
            api_key=settings.ai_api_key.get_secret_value() if settings.ai_api_key else None,
            model=settings.ai_model,
            timeout=settings.provider_timeout_seconds,
        )
        screenshot_service = ScreenshotService(
            url=(str(settings.screenshot_service_url) if settings.screenshot_service_url else None),
            token=(
                settings.screenshot_service_token.get_secret_value()
                if settings.screenshot_service_token
                else None
            ),
        )
        self.github_authenticated = github_client.is_authenticated
        self.gitlab_authenticated = gitlab_client.is_authenticated
        self.bitbucket_authenticated = bitbucket_client.is_authenticated
        self.ai_metadata_enabled = ai_enricher.enabled
        self.screenshot_service_enabled = screenshot_service.enabled
        self.screenshot_service = screenshot_service
        self.local_upload_enabled = settings.local_upload_enabled
        self.local_upload_max_bytes = settings.local_upload_max_bytes
        self.local_upload_max_uncompressed_bytes = settings.local_upload_max_uncompressed_bytes
        self.local_upload_max_entries = settings.local_upload_max_entries
        self.adapter_names = adapters.names
        self.template_import_service = TemplateImportService(
            async_session_factory,
            adapters,
            analyzer,
            ai_enricher,
            screenshot_service,
        )
        self.template_sync_service = TemplateSyncService(
            async_session_factory,
            adapters,
            analyzer,
            ai_enricher,
        )
        self._async_clients = [gitlab_client, bitbucket_client]

    async def close(self) -> None:
        for client in self._async_clients:
            await client.close()
