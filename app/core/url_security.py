import ipaddress
from urllib.parse import urlsplit

from app.core.exceptions import ValidationError

_BLOCKED_HOSTS = {"localhost", "localhost.localdomain", "metadata.google.internal"}
_BLOCKED_SUFFIXES = (".local", ".internal", ".localhost")


def validate_public_https_url(value: str, *, field_name: str = "URL") -> str:
    url = value.strip()
    if len(url) > 1000:
        raise ValidationError(f"{field_name} is too long")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValidationError(f"{field_name} must be an absolute HTTPS URL")
    if parsed.username or parsed.password or parsed.port not in {None, 443}:
        raise ValidationError(f"{field_name} cannot contain credentials or a custom port")
    host = parsed.hostname.casefold().rstrip(".")
    if host in _BLOCKED_HOSTS or host.endswith(_BLOCKED_SUFFIXES):
        raise ValidationError(f"{field_name} cannot target a local or internal host")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    ):
        raise ValidationError(f"{field_name} cannot target a private or reserved address")
    return url
