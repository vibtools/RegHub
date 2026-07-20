from app.core.config import Settings
from app.database.session import async_session_factory
from app.integrations.github.client import GitHubClient
from app.registry.adapters.github import GitHubRegistryAdapter
from app.registry.adapters.registry import AdapterRegistry
from app.registry.template import TemplateImportService


class ApplicationContainer:
    def __init__(self, settings: Settings) -> None:
        github_client = GitHubClient(
            token=settings.github_token.get_secret_value() if settings.github_token else None,
            timeout=settings.github_timeout_seconds,
            allow_private=settings.github_allow_private_repositories,
        )
        adapters = AdapterRegistry([GitHubRegistryAdapter(github_client)])
        self.template_import_service = TemplateImportService(async_session_factory, adapters)
