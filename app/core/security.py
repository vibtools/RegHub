import hashlib
import hmac
from dataclasses import asdict, dataclass
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

_ADMIN_COOKIE_VERSION = 2


@dataclass(frozen=True, slots=True)
class AdminIdentity:
    subject: str
    email: str | None
    name: str | None
    claims: dict[str, Any]
    roles: tuple[str, ...] = ()


def derive_secret(secret: str, purpose: str) -> str:
    """Derive independent key material from the deployment secret.

    The derivation is deterministic so the existing deployment workflow does not need another
    environment value, while each security boundary receives unrelated key material.
    """

    normalized_purpose = purpose.strip().casefold()
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789-_."
    if not normalized_purpose or any(ch not in allowed for ch in normalized_purpose):
        raise ValueError("Key-derivation purpose contains unsupported characters")
    context = f"reghub-key-v1:{normalized_purpose}".encode()
    return hmac.new(secret.encode("utf-8"), context, hashlib.sha256).hexdigest()


class AdminTokenSigner:
    def __init__(self, secret: str, salt: str = "reghub-admin-cookie-v2") -> None:
        self._serializer = URLSafeTimedSerializer(
            secret_key=derive_secret(secret, "admin-auth-cookie"),
            salt=salt,
        )

    def issue(self, identity: AdminIdentity) -> str:
        payload = asdict(identity)
        payload["version"] = _ADMIN_COOKIE_VERSION
        return self._serializer.dumps(payload)

    def verify(self, token: str, max_age: int) -> AdminIdentity | None:
        try:
            payload = self._serializer.loads(token, max_age=max_age)
        except (BadSignature, SignatureExpired):
            return None
        if (
            not isinstance(payload, dict)
            or payload.get("version") != _ADMIN_COOKIE_VERSION
            or not isinstance(payload.get("subject"), str)
            or not payload["subject"].strip()
        ):
            return None
        raw_roles = payload.get("roles")
        roles = (
            tuple(dict.fromkeys(item for item in raw_roles if isinstance(item, str) and item))
            if isinstance(raw_roles, list)
            else ()
        )
        # Never infer a privileged role from a legacy or malformed cookie. Authentication must be
        # re-established through OIDC when role data is absent.
        if not roles:
            return None
        return AdminIdentity(
            subject=payload["subject"],
            email=payload.get("email") if isinstance(payload.get("email"), str) else None,
            name=payload.get("name") if isinstance(payload.get("name"), str) else None,
            claims=payload.get("claims") if isinstance(payload.get("claims"), dict) else {},
            roles=roles,
        )


def get_nested_claim(claims: dict[str, Any], dotted_name: str) -> Any:
    value: Any = claims
    for part in dotted_name.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def sanitize_relative_redirect(value: str | None, default: str = "/admin") -> str:
    if not value or not value.startswith("/") or value.startswith("//"):
        return default
    if "\\" in value or any(ord(char) < 32 for char in value):
        return default
    return value
