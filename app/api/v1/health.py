from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.dependencies import DatabaseSession

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "reghub"}


@router.get("/ready")
async def ready(request: Request, session: DatabaseSession):
    await session.execute(text("SELECT 1"))
    container = request.app.state.container
    worker_status = await container.operation_runner.worker_status()
    payload: dict[str, object] = {
        "status": "ready",
        "database": "ok",
        "operation_backend": container.settings.operation_backend,
        "operation_worker": worker_status or "not-configured",
        "cache_backend": container.catalog_cache.backend_name,
        "rate_limit_backend": container.rate_limiter.backend_name,
    }
    if container.settings.operation_backend == "redis" and not worker_status:
        payload["status"] = "degraded"
        payload["operation_worker"] = "heartbeat-missing"
        return JSONResponse(payload, status_code=503)
    return payload
