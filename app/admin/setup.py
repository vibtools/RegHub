from fastapi import FastAPI

from app.admin.application import RegistryAdmin
from app.admin.authentication import OIDCAdminAuthentication
from app.admin.views import (
    AssetGalleryView,
    AuditEventAdmin,
    CategoryAdmin,
    FrameworkAdmin,
    GitHubImportView,
    GovernanceView,
    ImportHistoryAdmin,
    LocalImportView,
    OperationsConsoleView,
    ProviderAdmin,
    RegistryImportView,
    ScreenshotJobAdmin,
    SettingsView,
    SyncHistoryAdmin,
    TemplateAdmin,
    TemplateAssetAdmin,
    TemplateVersionAdmin,
)
from app.database.engine import engine


def setup_admin(app: FastAPI) -> RegistryAdmin:
    admin = RegistryAdmin(
        app=app,
        engine=engine,
        title="RegHub",
        base_url="/admin",
        templates_dir="templates",
        authentication_backend=OIDCAdminAuthentication(),
    )
    for view in [
        OperationsConsoleView,
        GovernanceView,
        SettingsView,
        GitHubImportView,
        RegistryImportView,
        LocalImportView,
        AssetGalleryView,
        TemplateAdmin,
        CategoryAdmin,
        ProviderAdmin,
        FrameworkAdmin,
        ImportHistoryAdmin,
        SyncHistoryAdmin,
        TemplateVersionAdmin,
        TemplateAssetAdmin,
        ScreenshotJobAdmin,
        AuditEventAdmin,
    ]:
        admin.add_view(view)
    return admin
