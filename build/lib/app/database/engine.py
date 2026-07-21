from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import get_settings


def create_engine() -> AsyncEngine:
    settings = get_settings()
    kwargs: dict[str, object] = {
        "pool_pre_ping": True,
        "echo": settings.app_debug,
    }
    if settings.database_url.startswith("postgresql"):
        kwargs.update(
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_recycle=1800,
        )
    return create_async_engine(settings.database_url, **kwargs)


engine = create_engine()
