import ipaddress
from collections.abc import Iterable
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send


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
        if not value:
            return False
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            return False
        return any(address in network for network in self.networks)

    def _client_from_chain(self, forwarded: str, peer: str | None) -> str | None:
        values = [item.strip() for item in forwarded.split(",") if item.strip()]
        if not values:
            return peer
        if self.trust_all:
            return values[0]
        chain = [*values, *([peer] if peer else [])]
        for value in reversed(chain):
            if not self._trusted(value):
                return value
        return values[0]

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
        forwarded_host = decoded.get(b"x-forwarded-host", b"").decode("latin-1").split(",", 1)[0]
        if forwarded_host:
            headers = [(key, value) for key, value in headers if key.lower() != b"host"]
            headers.append((b"host", forwarded_host.encode("latin-1")))
            scope["headers"] = headers
        await self.app(scope, receive, send)
