import ipaddress
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Receive, Scope, Send


def _normalized_ip(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def _validated_forwarded_host(value: str) -> str | None:
    candidate = value.strip()
    if not candidate or len(candidate) > 255:
        return None
    if any(character.isspace() or ord(character) < 33 for character in candidate):
        return None
    if any(token in candidate for token in ("/", "\\", "@", "?", "#")):
        return None
    try:
        parsed = urlsplit(f"//{candidate}")
        _ = parsed.port
    except ValueError:
        return None
    if not parsed.hostname or parsed.username or parsed.password:
        return None
    return candidate


class TrustedProxyHeadersMiddleware:
    """Apply forwarding headers only when the immediate proxy is trusted."""

    def __init__(self, app: ASGIApp, trusted_networks: Iterable[str]) -> None:
        self.app = app
        values = [item.strip() for item in trusted_networks if item.strip()]
        self.trust_all = "*" in values
        self.networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for value in values:
            if value == "*":
                continue
            try:
                self.networks.append(ipaddress.ip_network(value, strict=False))
            except ValueError:
                continue

    def _trusted(self, value: str | None) -> bool:
        if self.trust_all:
            return True
        normalized = _normalized_ip(value)
        if normalized is None:
            return False
        address = ipaddress.ip_address(normalized)
        return any(address in network for network in self.networks)

    def _client_from_chain(self, forwarded: str, peer: str | None) -> str | None:
        raw_values = [item.strip() for item in forwarded.split(",") if item.strip()]
        if not raw_values:
            return _normalized_ip(peer)
        values = [_normalized_ip(item) for item in raw_values]
        if any(item is None for item in values):
            return _normalized_ip(peer)
        normalized_values = [item for item in values if item is not None]
        if self.trust_all:
            return normalized_values[0]
        normalized_peer = _normalized_ip(peer)
        chain = [*normalized_values, *([normalized_peer] if normalized_peer else [])]
        for value in reversed(chain):
            if not self._trusted(value):
                return value
        return normalized_values[0]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        peer = scope.get("client")
        peer_host = peer[0] if peer else None
        state: dict[str, Any] = scope.setdefault("state", {})
        state["proxy_peer"] = peer_host
        state["proxy_trusted"] = self._trusted(peer_host)
        if not state["proxy_trusted"]:
            await self.app(scope, receive, send)
            return

        headers = list(scope.get("headers", []))
        decoded = {key.lower(): value for key, value in headers}
        forwarded_for = decoded.get(b"x-forwarded-for", b"").decode("latin-1")
        client = self._client_from_chain(forwarded_for, peer_host)
        if client:
            scope["client"] = (client, peer[1] if peer else 0)
        proto = decoded.get(b"x-forwarded-proto", b"").decode("latin-1").split(",", 1)[0]
        if proto in {"http", "https", "ws", "wss"}:
            scope["scheme"] = proto
        raw_host = decoded.get(b"x-forwarded-host", b"").decode("latin-1").split(",", 1)[0]
        forwarded_host = _validated_forwarded_host(raw_host)
        state["forwarded_host_accepted"] = forwarded_host is not None
        if forwarded_host:
            headers = [(key, value) for key, value in headers if key.lower() != b"host"]
            headers.append((b"host", forwarded_host.encode("latin-1")))
            scope["headers"] = headers
        await self.app(scope, receive, send)
