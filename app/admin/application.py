from sqladmin import Admin
from sqladmin.authentication import login_required
from sqlalchemy import func, select
from starlette.requests import Request
from starlette.responses import Response

from app.core.enums import ImportStatus, TemplateStatus
from app.models.category import Category
from app.models.framework import Framework
from app.models.import_history import ImportHistory
from app.models.provider import Provider
from app.models.template import Template


class RegistryAdmin(Admin):
    @login_required
    async def index(self, request: Request) -> Response:
        async with self.session_maker() as session:
            context = {
                "title": "Registry Dashboard",
                "template_count": int(await session.scalar(select(func.count(Template.id))) or 0),
                "published_count": int(
                    await session.scalar(
                        select(func.count(Template.id)).where(
                            Template.status == TemplateStatus.PUBLISHED
                        )
                    )
                    or 0
                ),
                "category_count": int(await session.scalar(select(func.count(Category.id))) or 0),
                "provider_count": int(await session.scalar(select(func.count(Provider.id))) or 0),
                "framework_count": int(await session.scalar(select(func.count(Framework.id))) or 0),
                "failed_import_count": int(
                    await session.scalar(
                        select(func.count(ImportHistory.id)).where(
                            ImportHistory.status == ImportStatus.FAILED
                        )
                    )
                    or 0
                ),
            }
        return await self.templates.TemplateResponse(request, "sqladmin/index.html", context)
