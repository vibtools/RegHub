from fastapi import APIRouter, Query, Request, Response

from app.api.dependencies import DatabaseSession
from app.core.config import get_settings
from app.registry.category import CategoryService
from app.registry.framework import FrameworkService
from app.registry.provider import ProviderService
from app.registry.template import TemplateService
from app.schemas.catalog import (
    CapabilitiesRead,
    CategoryRead,
    FrameworkRead,
    PaginationMeta,
    ProviderRead,
    ResponseMeta,
    TemplateDetail,
    TemplatePage,
)
from app.schemas.manifest import TemplateManifest

router = APIRouter(tags=["registry"])


def _cache(response: Response) -> None:
    seconds = get_settings().public_api_cache_seconds
    response.headers["Cache-Control"] = f"public, max-age={seconds}, stale-while-revalidate=30"


@router.get("/templates", response_model=TemplatePage)
async def list_templates(
    request: Request,
    response: Response,
    session: DatabaseSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, min_length=1, max_length=100),
    category: str | None = Query(default=None, max_length=120),
    provider: str | None = Query(default=None, max_length=140),
    framework: str | None = Query(default=None, max_length=120),
    featured: bool | None = None,
):
    records, total, pages = await TemplateService.list_public(
        session,
        page=page,
        page_size=page_size,
        search=search,
        category=category,
        provider=provider,
        framework=framework,
        featured=featured,
    )
    _cache(response)
    return TemplatePage(
        data=records,
        pagination=PaginationMeta(
            page=page, page_size=page_size, total_items=total, total_pages=pages
        ),
        meta=ResponseMeta(request_id=request.state.request_id),
    )


@router.get("/templates/{slug}", response_model=TemplateDetail)
async def template_detail(slug: str, response: Response, session: DatabaseSession):
    template = await TemplateService.get_public_by_slug(session, slug)
    _cache(response)
    return template


@router.get("/templates/{slug}/manifest", response_model=TemplateManifest)
async def template_manifest(slug: str, response: Response, session: DatabaseSession):
    template = await TemplateService.get_public_by_slug(session, slug)
    _cache(response)
    return template.manifest


@router.get("/categories", response_model=list[CategoryRead])
async def categories(response: Response, session: DatabaseSession):
    _cache(response)
    return await CategoryService.list_active(session)


@router.get("/providers", response_model=list[ProviderRead])
async def providers(response: Response, session: DatabaseSession):
    _cache(response)
    return await ProviderService.list_active(session)


@router.get("/frameworks", response_model=list[FrameworkRead])
async def frameworks(response: Response, session: DatabaseSession):
    _cache(response)
    return await FrameworkService.list_active(session)


@router.get("/capabilities", response_model=CapabilitiesRead)
async def capabilities(request: Request, response: Response):
    _cache(response)
    container = request.app.state.container
    return CapabilitiesRead(
        version="0.2.0",
        registry_adapters=[*container.adapter_names, "local-manifest", "local-zip"],
        framework_detection=[
            "astro",
            "nextjs",
            "react-vite",
            "react",
            "vue",
            "nuxt",
            "sveltekit",
            "laravel",
            "django",
            "fastapi",
            "static-html",
            "docker",
        ],
        manifest_versions=["1.0", "2.0"],
        local_upload_enabled=container.local_upload_enabled,
        ai_metadata_enabled=container.ai_metadata_enabled,
        screenshot_service_enabled=container.screenshot_service_enabled,
    )
