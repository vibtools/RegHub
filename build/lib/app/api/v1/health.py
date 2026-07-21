from fastapi import APIRouter
from sqlalchemy import text

from app.api.dependencies import DatabaseSession

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "reghub"}


@router.get("/ready")
async def ready(session: DatabaseSession) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok"}
