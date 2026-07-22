from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from app.core.config import get_settings
from app.core.security import AdminTokenSigner, derive_secret


class OIDCAdminAuthentication(AuthenticationBackend):
    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(
            secret_key=derive_secret(
                settings.session_secret.get_secret_value(), "sqladmin-aux-session"
            ),
            session_cookie="reghub_admin_aux",
            same_site="lax",
            https_only=settings.session_cookie_secure,
            max_age=settings.session_max_age_seconds,
        )
        self._settings = settings
        self._signer = AdminTokenSigner(settings.session_secret.get_secret_value())

    async def login(self, request: Request) -> Response:
        return RedirectResponse("/auth/login?next=/admin", status_code=302)

    async def logout(self, request: Request) -> Response:
        # Use the canonical logout route so the OIDC state, SQLAdmin auxiliary session and
        # administrator authentication cookie are cleared together.
        return RedirectResponse("/auth/logout", status_code=302)

    async def authenticate(self, request: Request) -> bool:
        token = request.cookies.get("reghub_auth")
        if not token:
            return False
        identity = self._signer.verify(token, self._settings.session_max_age_seconds)
        if identity is None or not identity.roles:
            return False
        request.state.admin_identity = identity
        return True
