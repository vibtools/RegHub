from collections.abc import Iterable
from typing import Any, Final

from starlette.requests import Request

from app.core.config import Settings
from app.core.exceptions import PermissionDeniedError
from app.core.security import AdminIdentity, get_nested_claim

ROLE_PERMISSIONS: Final[dict[str, frozenset[str]]] = {
    "viewer": frozenset({"registry.read"}),
    "editor": frozenset(
        {
            "registry.read",
            "templates.write",
            "imports.run",
            "sync.run",
            "media.write",
            "operations.run",
        }
    ),
    "publisher": frozenset(
        {
            "registry.read",
            "templates.write",
            "imports.run",
            "sync.run",
            "media.write",
            "publication.manage",
            "operations.run",
        }
    ),
    "security_admin": frozenset(
        {
            "registry.read",
            "settings.manage",
            "api.manage",
            "audit.read",
            "operations.manage",
            "operations.run",
        }
    ),
    "super_admin": frozenset({"*"}),
}


def _claim_values(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value.casefold()}
    if isinstance(value, (list, tuple, set)):
        return {str(item).casefold() for item in value if isinstance(item, str)}
    return set()


def resolve_roles(claims: dict[str, Any], settings: Settings) -> tuple[str, ...]:
    claim_values = _claim_values(get_nested_claim(claims, settings.oidc_role_claim))
    legacy_values = _claim_values(get_nested_claim(claims, settings.oidc_admin_claim))
    roles: set[str] = set()

    legacy_admins = {item.casefold() for item in settings.oidc_admin_values}
    if legacy_values & legacy_admins:
        roles.add("super_admin")

    for role, external_values in settings.oidc_role_values.items():
        if role not in ROLE_PERMISSIONS:
            continue
        allowed = {item.casefold() for item in external_values}
        if claim_values & allowed or legacy_values & allowed:
            roles.add(role)

    return tuple(sorted(roles))


def permissions_for_roles(roles: Iterable[str]) -> frozenset[str]:
    permissions: set[str] = set()
    for role in roles:
        permissions.update(ROLE_PERMISSIONS.get(role, frozenset()))
    return frozenset(permissions)


def has_permission(identity: AdminIdentity, permission: str) -> bool:
    permissions = permissions_for_roles(identity.roles)
    return "*" in permissions or permission in permissions


def require_permission(request: Request, permission: str) -> AdminIdentity:
    identity = getattr(request.state, "admin_identity", None)
    if not isinstance(identity, AdminIdentity):
        raise PermissionDeniedError("Administrator authentication is required")
    if not has_permission(identity, permission):
        raise PermissionDeniedError(f"This administrator role does not permit '{permission}'")
    return identity
