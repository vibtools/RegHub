from authlib.integrations.starlette_client import OAuth

from app.core.config import Settings


def build_oauth(settings: Settings) -> OAuth:
    oauth = OAuth()
    if settings.oidc_enabled:
        oauth.register(
            name="vib_auth",
            client_id=settings.oidc_client_id,
            client_secret=settings.oidc_client_secret.get_secret_value()
            if settings.oidc_client_secret
            else None,
            server_metadata_url=(
                f"{str(settings.oidc_issuer_url).rstrip('/')}/.well-known/openid-configuration"
            ),
            client_kwargs={
                "scope": settings.oidc_scopes,
                "code_challenge_method": "S256",
            },
        )
    return oauth
