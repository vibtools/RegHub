from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from app.core.config import Settings, get_settings
from app.core.security import (
    AdminIdentity,
    AdminTokenSigner,
    claim_matches,
    get_nested_claim,
    sanitize_relative_redirect,
)
from app.governance.rbac import resolve_roles

router = APIRouter(prefix="/auth", tags=["authentication"])


def _signer() -> AdminTokenSigner:
    settings = get_settings()
    return AdminTokenSigner(settings.session_secret.get_secret_value())


def _identity_from_claims(claims: dict[str, Any], settings: Settings) -> AdminIdentity:
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise HTTPException(status_code=401, detail="OIDC identity does not contain a subject")
    return AdminIdentity(
        subject=subject,
        email=claims.get("email") if isinstance(claims.get("email"), str) else None,
        name=claims.get("name") if isinstance(claims.get("name"), str) else None,
        claims={},
        roles=resolve_roles(claims, settings),
    )


@router.get("/login", name="auth_login")
async def login(request: Request, next: str | None = None):
    settings = get_settings()
    if not settings.oidc_enabled:
        raise HTTPException(status_code=503, detail="OIDC is not configured")
    request.session["post_login_redirect"] = sanitize_relative_redirect(next)
    redirect_uri = f"{settings.base_url}/auth/callback"
    client = request.app.state.oauth.create_client("vib_auth")
    if client is None:
        raise HTTPException(status_code=503, detail="OIDC client is unavailable")
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/callback", name="auth_callback")
async def callback(request: Request):
    settings = get_settings()
    client = request.app.state.oauth.create_client("vib_auth")
    if client is None:
        raise HTTPException(status_code=503, detail="OIDC client is unavailable")
    try:
        token = await client.authorize_access_token(request)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="OIDC login failed") from exc

    claims = token.get("userinfo")
    if not isinstance(claims, dict):
        claims = await client.userinfo(token=token)
        claims = dict(claims)
    claim_value = get_nested_claim(claims, settings.oidc_admin_claim)
    identity = _identity_from_claims(claims, settings)
    legacy_authorized = claim_matches(claim_value, settings.oidc_admin_values)
    if not legacy_authorized and not identity.roles:
        await request.app.state.container.audit.append(
            action="auth.login",
            resource_type="administrator_session",
            resource_id=identity.subject,
            outcome="denied",
            actor_subject=identity.subject,
            actor_email=identity.email,
            request=request,
            details={"reason": "No authorized RegHub role"},
        )
        raise HTTPException(status_code=403, detail="This identity is not authorized for RegHub")
    await request.app.state.container.audit.append(
        action="auth.login",
        resource_type="administrator_session",
        resource_id=identity.subject,
        identity=identity,
        request=request,
    )
    target = sanitize_relative_redirect(request.session.pop("post_login_redirect", None))
    response = RedirectResponse(target, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="reghub_auth",
        value=_signer().issue(identity),
        max_age=settings.session_max_age_seconds,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/logout", name="auth_logout")
async def logout(request: Request):
    settings = get_settings()
    token = request.cookies.get("reghub_auth")
    identity = _signer().verify(token, settings.session_max_age_seconds) if token else None
    if identity is not None:
        await request.app.state.container.audit.append(
            action="auth.logout",
            resource_type="administrator_session",
            resource_id=identity.subject,
            identity=identity,
            request=request,
        )
    response = RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("reghub_auth", path="/")
    return response


@router.get("/me")
async def me(request: Request):
    settings = get_settings()
    token = request.cookies.get("reghub_auth")
    identity = _signer().verify(token, settings.session_max_age_seconds) if token else None
    if identity is None:
        return JSONResponse({"authenticated": False}, status_code=401)
    return {
        "authenticated": True,
        "subject": identity.subject,
        "email": identity.email,
        "name": identity.name,
        "roles": list(identity.roles),
    }
