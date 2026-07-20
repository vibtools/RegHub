from fastapi import FastAPI

from app.admin.application import RegistryAdmin
from app.admin.authentication import OIDCAdminAuthentication
from app.admin.views import (
    CategoryAdmin,
    FrameworkAdmin,
    GitHubImportView,
    ImportHistoryAdmin,
    ProviderAdmin,
    TemplateAdmin,
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
        GitHubImportView,
        TemplateAdmin,
        CategoryAdmin,
        ProviderAdmin,
        FrameworkAdmin,
        ImportHistoryAdmin,
    ]:
        admin.add_view(view)
    return admin
