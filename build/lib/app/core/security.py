from dataclasses import asdict, dataclass
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


@dataclass(frozen=True, slots=True)
class AdminIdentity:
    subject: str
    email: str | None
    name: str | None
    claims: dict[str, Any]


class AdminTokenSigner:
    def __init__(self, secret: str, salt: str = "reghub-admin-cookie-v1") -> None:
        self._serializer = URLSafeTimedSerializer(secret_key=secret, salt=salt)

    def issue(self, identity: AdminIdentity) -> str:
        return self._serializer.dumps(asdict(identity))

    def verify(self, token: str, max_age: int) -> AdminIdentity | None:
        try:
            payload = self._serializer.loads(token, max_age=max_age)
        except (BadSignature, SignatureExpired):
            return None
        if not isinstance(payload, dict) or not isinstance(payload.get("subject"), str):
            return None
        return AdminIdentity(
            subject=payload["subject"],
            email=payload.get("email"),
            name=payload.get("name"),
            claims=payload.get("claims") if isinstance(payload.get("claims"), dict) else {},
        )


def get_nested_claim(claims: dict[str, Any], dotted_name: str) -> Any:
    value: Any = claims
    for part in dotted_name.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def claim_matches(value: Any, allowed_values: list[str]) -> bool:
    allowed = {item.casefold() for item in allowed_values}
    if isinstance(value, str):
        return value.casefold() in allowed
    if isinstance(value, list):
        return any(isinstance(item, str) and item.casefold() in allowed for item in value)
    return False


def sanitize_relative_redirect(value: str | None, default: str = "/admin") -> str:
    if not value or not value.startswith("/") or value.startswith("//"):
        return default
    return value
