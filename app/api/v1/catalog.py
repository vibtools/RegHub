import hashlib
import logging
from datetime import UTC, datetime
from email.utils import format_datetime

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from app.api.dependencies import DatabaseSession
from app.core.config import get_settings
from app.registry.category import CategoryService
from app.registry.framework import FrameworkService
from app.registry.provider import ProviderService
from app.registry.template import TemplateService
from app.schemas.catalog import (
    AssetListResponse,
    CapabilitiesRead,
    CategoryRead,
    FacetsResponse,
    FrameworkRead,
    FreshnessResponse,
    PaginationMeta,
    ProviderRead,
    RepositoryRead,
    RepositoryResponse,
    ResponseMeta,
    TemplateDetail,
    TemplatePage,
)
from app.schemas.manifest import TemplateManifest

router = APIRouter(tags=["registry"])
logger = logging.getLogger(__name__)


def _cache_key(request: Request, namespace: str) -> str:
    raw = f"{namespace}:{request.url.path}?{request.url.query}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _catalog_cache(request: Request):
    container = getattr(request.app.state, "container", None)
    return getattr(container, "catalog_cache", None)


async def _cache_get(request: Request, response: Response, namespace: str, adapter: TypeAdapter):
    cache = _catalog_cache(request)
    if cache is None:
        response.headers["X-RegHub-Cache"] = "BYPASS"
        return None
    try:
        payload = await cache.get_json(_cache_key(request, namespace))
    except Exception:
        # Cache infrastructure is an optimization. A transient Redis/cache failure must not
        # turn a healthy registry database request into an API outage.
        logger.exception("Catalog cache read failed for namespace %s", namespace)
        response.headers["X-RegHub-Cache"] = "BYPASS"
        return None
    if payload is None:
        response.headers["X-RegHub-Cache"] = "MISS"
        return None
    try:
        value = adapter.validate_python(payload)
    except (PydanticValidationError, TypeError, ValueError):
        # A deployment can change an additive response model while an older cache entry remains.
        # Treat incompatible cached data as a miss instead of failing a public API request.
        response.headers["X-RegHub-Cache"] = "STALE"
        return None
    response.headers["X-RegHub-Cache"] = "HIT"
    if isinstance(value, BaseModel) and hasattr(value, "meta"):
        value = value.model_copy(update={"meta": ResponseMeta(request_id=request.state.request_id)})
    return value


async def _cache_set(request: Request, namespace: str, adapter: TypeAdapter, value: object) -> None:
    cache = _catalog_cache(request)
    if cache is None:
        return
    validated = adapter.validate_python(value)
    try:
        await cache.set_json(
            _cache_key(request, namespace),
            adapter.dump_python(validated, mode="json"),
        )
    except Exception:
        # Public responses are authoritative from PostgreSQL; cache write failure is non-fatal.
        logger.exception("Catalog cache write failed for namespace %s", namespace)


_TEMPLATE_PAGE = TypeAdapter(TemplatePage)
_TEMPLATE_DETAIL = TypeAdapter(TemplateDetail)
_MANIFEST = TypeAdapter(TemplateManifest)
_REPOSITORY = TypeAdapter(RepositoryResponse)
_ASSETS = TypeAdapter(AssetListResponse)
_FRESHNESS = TypeAdapter(FreshnessResponse)
_FACETS = TypeAdapter(FacetsResponse)
_CATEGORIES = TypeAdapter(list[CategoryRead])
_PROVIDERS = TypeAdapter(list[ProviderRead])
_FRAMEWORKS = TypeAdapter(list[FrameworkRead])
_CAPABILITIES = TypeAdapter(CapabilitiesRead)


async def _require_api(request: Request, feature: str, scope: str) -> None:
    container = request.app.state.container
    container.require_feature("public_api")
    container.require_feature(feature)
    await container.api_access.authorize(request, scope)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _cache(response: Response) -> None:
    seconds = get_settings().public_api_cache_seconds
    response.headers["Cache-Control"] = f"public, max-age={seconds}, stale-while-revalidate=30"


def _entity_headers(
    request: Request, response: Response, identity: str, updated_at: datetime
) -> bool:
    normalized = (
        updated_at.replace(tzinfo=UTC) if updated_at.tzinfo is None else updated_at.astimezone(UTC)
    )
    digest = hashlib.sha256(f"{identity}:{normalized.isoformat()}".encode()).hexdigest()[:24]
    etag = f'"{digest}"'
    response.headers["ETag"] = etag
    response.headers["Last-Modified"] = format_datetime(normalized, usegmt=True)
    response.headers["Vary"] = "Accept, Origin"
    return request.headers.get("if-none-match") == etag


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
    tag: str | None = Query(default=None, max_length=80),
    language: str | None = Query(default=None, max_length=100),
    difficulty: str | None = Query(default=None, max_length=32),
    use_case: str | None = Query(default=None, max_length=160),
    min_quality: int | None = Query(default=None, ge=0, le=100),
    updated_since: datetime | None = Query(default=None),
    sort: str = Query(default="featured", pattern="^(featured|newest|updated|quality|stars|name)$"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
):
    await _require_api(request, "api_catalog", "catalog")
    cached = await _cache_get(request, response, "templates", _TEMPLATE_PAGE)
    if cached is not None:
        _cache(response)
        return cached
    records, total, pages = await TemplateService.list_public(
        session,
        page=page,
        page_size=page_size,
        search=search,
        category=category,
        provider=provider,
        framework=framework,
        featured=featured,
        tag=tag,
        language=language,
        difficulty=difficulty,
        use_case=use_case,
        min_quality=min_quality,
        updated_since=_as_utc(updated_since),
        sort=sort,
        order=order,
    )
    _cache(response)
    result = TemplatePage(
        data=records,
        pagination=PaginationMeta(
            page=page, page_size=page_size, total_items=total, total_pages=pages
        ),
        meta=ResponseMeta(request_id=request.state.request_id),
    )
    await _cache_set(request, "templates", _TEMPLATE_PAGE, result)
    return result


@router.get("/templates/changes", response_model=TemplatePage)
async def template_changes(
    request: Request,
    response: Response,
    session: DatabaseSession,
    updated_since: datetime = Query(...),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=100),
):
    await _require_api(request, "api_changes", "changes")
    records, total, pages = await TemplateService.list_public(
        session,
        page=page,
        page_size=page_size,
        search=None,
        category=None,
        provider=None,
        framework=None,
        featured=None,
        updated_since=_as_utc(updated_since),
        sort="updated",
        order="asc",
    )
    response.headers["Cache-Control"] = "no-cache"
    return TemplatePage(
        data=records,
        pagination=PaginationMeta(
            page=page, page_size=page_size, total_items=total, total_pages=pages
        ),
        meta=ResponseMeta(request_id=request.state.request_id),
    )


@router.get("/templates/{slug}", response_model=TemplateDetail)
async def template_detail(
    slug: str, request: Request, response: Response, session: DatabaseSession
):
    await _require_api(request, "api_catalog", "catalog")
    cached = await _cache_get(request, response, "template-detail", _TEMPLATE_DETAIL)
    if cached is not None:
        _cache(response)
        if _entity_headers(request, response, str(cached.id), cached.updated_at):
            return Response(status_code=304, headers=dict(response.headers))
        return cached
    template = await TemplateService.get_public_by_slug(session, slug)
    _cache(response)
    if _entity_headers(request, response, str(template.id), template.updated_at):
        return Response(status_code=304, headers=dict(response.headers))
    result = _TEMPLATE_DETAIL.validate_python(template)
    await _cache_set(request, "template-detail", _TEMPLATE_DETAIL, result)
    return result


@router.get("/templates/{slug}/manifest", response_model=TemplateManifest)
async def template_manifest(
    slug: str, request: Request, response: Response, session: DatabaseSession
):
    await _require_api(request, "api_catalog", "catalog")
    cached = await _cache_get(request, response, "template-manifest", _MANIFEST)
    template = await TemplateService.get_public_by_slug(session, slug)
    _cache(response)
    if _entity_headers(request, response, f"manifest:{template.id}", template.updated_at):
        return Response(status_code=304, headers=dict(response.headers))
    if cached is not None:
        return cached
    result = _MANIFEST.validate_python(template.manifest)
    await _cache_set(request, "template-manifest", _MANIFEST, result)
    return result


@router.get("/templates/{slug}/repository", response_model=RepositoryResponse)
async def template_repository(
    slug: str, request: Request, response: Response, session: DatabaseSession
):
    await _require_api(request, "api_catalog", "catalog")
    template = await TemplateService.get_public_by_slug(session, slug)
    repository = await TemplateService.public_repository(session, slug)
    _cache(response)
    if _entity_headers(request, response, f"repository:{template.id}", template.updated_at):
        return Response(status_code=304, headers=dict(response.headers))
    cached = await _cache_get(request, response, "template-repository", _REPOSITORY)
    if cached is not None:
        return cached
    result = RepositoryResponse(
        data=RepositoryRead(**repository),
        meta=ResponseMeta(request_id=request.state.request_id),
    )
    await _cache_set(request, "template-repository", _REPOSITORY, result)
    return result


@router.get("/templates/{slug}/assets", response_model=AssetListResponse)
async def template_assets(
    slug: str, request: Request, response: Response, session: DatabaseSession
):
    await _require_api(request, "api_assets", "assets")
    cached = await _cache_get(request, response, "template-assets", _ASSETS)
    if cached is not None:
        _cache(response)
        return cached
    assets = await TemplateService.list_public_assets(session, slug)
    _cache(response)
    result = AssetListResponse(
        data=assets,
        meta=ResponseMeta(request_id=request.state.request_id),
    )
    await _cache_set(request, "template-assets", _ASSETS, result)
    return result


@router.get("/templates/{slug}/freshness", response_model=FreshnessResponse)
async def template_freshness(
    slug: str, request: Request, response: Response, session: DatabaseSession
):
    await _require_api(request, "api_freshness", "freshness")
    cached = await _cache_get(request, response, "template-freshness", _FRESHNESS)
    if cached is not None:
        response.headers["Cache-Control"] = "public, max-age=30, stale-while-revalidate=30"
        return cached
    freshness = await TemplateService.public_freshness(session, slug)
    response.headers["Cache-Control"] = "public, max-age=30, stale-while-revalidate=30"
    result = FreshnessResponse(
        data=freshness,
        meta=ResponseMeta(request_id=request.state.request_id),
    )
    await _cache_set(request, "template-freshness", _FRESHNESS, result)
    return result


@router.get("/facets", response_model=FacetsResponse)
async def facets(request: Request, response: Response, session: DatabaseSession):
    await _require_api(request, "api_facets", "facets")
    cached = await _cache_get(request, response, "facets", _FACETS)
    if cached is not None:
        _cache(response)
        return cached
    _cache(response)
    result = FacetsResponse(
        data=await TemplateService.public_facets(session),
        meta=ResponseMeta(request_id=request.state.request_id),
    )
    await _cache_set(request, "facets", _FACETS, result)
    return result


# Legacy v1 resource endpoints remain unchanged for backward compatibility.
@router.get("/categories", response_model=list[CategoryRead])
async def categories(request: Request, response: Response, session: DatabaseSession):
    await _require_api(request, "api_catalog", "catalog")
    cached = await _cache_get(request, response, "categories", _CATEGORIES)
    if cached is not None:
        _cache(response)
        return cached
    _cache(response)
    result = await CategoryService.list_active(session)
    await _cache_set(request, "categories", _CATEGORIES, result)
    return result


@router.get("/providers", response_model=list[ProviderRead])
async def providers(request: Request, response: Response, session: DatabaseSession):
    await _require_api(request, "api_catalog", "catalog")
    cached = await _cache_get(request, response, "providers", _PROVIDERS)
    if cached is not None:
        _cache(response)
        return cached
    _cache(response)
    result = await ProviderService.list_active(session)
    await _cache_set(request, "providers", _PROVIDERS, result)
    return result


@router.get("/frameworks", response_model=list[FrameworkRead])
async def frameworks(request: Request, response: Response, session: DatabaseSession):
    await _require_api(request, "api_catalog", "catalog")
    cached = await _cache_get(request, response, "frameworks", _FRAMEWORKS)
    if cached is not None:
        _cache(response)
        return cached
    _cache(response)
    result = await FrameworkService.list_active(session)
    await _cache_set(request, "frameworks", _FRAMEWORKS, result)
    return result


@router.get("/capabilities", response_model=CapabilitiesRead)
async def capabilities(request: Request, response: Response):
    container = request.app.state.container
    await _require_api(request, "api_catalog", "capabilities")
    cached = await _cache_get(request, response, "capabilities", _CAPABILITIES)
    if cached is not None:
        _cache(response)
        return cached
    _cache(response)
    result = CapabilitiesRead(
        version="0.3.1.1",
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
        provider_auto_create_enabled=container.feature_enabled("provider_auto_create"),
        media_gallery_enabled=container.feature_enabled("asset_gallery"),
        freshness_api_enabled=container.feature_enabled("api_freshness"),
        operations_console_enabled=container.feature_enabled("operations_console"),
        public_api_enabled=container.feature_enabled("public_api"),
        api_access_mode=container.api_access.mode,
        service_token_required=container.api_access.live_mode,
        operation_backend=container.operation_runner.effective_backend,
        cache_backend=container.catalog_cache.backend_name,
        rate_limit_backend=container.rate_limiter.backend_name,
        rbac_enabled=True,
        immutable_audit_enabled=True,
    )
    await _cache_set(request, "capabilities", _CAPABILITIES, result)
    return result
