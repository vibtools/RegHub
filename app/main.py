from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import RedirectResponse

from app.admin.setup import setup_admin
from app.api.errors import registry_error_handler, unexpected_error_handler
from app.api.v1.router import router as api_v1_router
from app.auth.oidc import build_oauth
from app.auth.routes import router as auth_router
from app.container import ApplicationContainer
from app.core.config import get_settings
from app.core.exceptions import RegistryError
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware, SecurityHeadersMiddleware
from app.database.engine import engine
from app.infrastructure.middleware import RateLimitMiddleware
from app.infrastructure.proxy import TrustedProxyHeadersMiddleware

settings = get_settings()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await app.state.container.initialize()
    yield
    await app.state.container.close()
    await engine.dispose()


app = FastAPI(
    title="RegHub API",
    version="0.3.0.3",
    description="Smart template registry API for YGIT",
    debug=settings.app_debug,
    lifespan=lifespan,
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url=None,
)

app.state.oauth = build_oauth(settings)
app.state.container = ApplicationContainer(settings)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret.get_secret_value(),
    session_cookie="reghub_oidc_state",
    max_age=600,
    same_site="lax",
    https_only=settings.session_cookie_secure,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Accept", "Content-Type", "X-Request-ID", "Authorization", "X-RegHub-Token"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    RateLimitMiddleware,
    service=app.state.container.rate_limiter,
    settings=settings,
)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    TrustedProxyHeadersMiddleware,
    trusted_networks=settings.trusted_proxy_networks,
)

app.add_exception_handler(RegistryError, registry_error_handler)
app.add_exception_handler(Exception, unexpected_error_handler)
app.include_router(auth_router)
app.include_router(api_v1_router)
setup_admin(app)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/admin", status_code=302)
