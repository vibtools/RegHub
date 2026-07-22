from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import Settings
from app.infrastructure.rate_limit import RateLimitResult, RateLimitService


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, service: RateLimitService, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.service = service
        self.settings = settings

    @staticmethod
    def _credential(request: Request) -> str | None:
        authorization = request.headers.get("authorization", "")
        if authorization.casefold().startswith("bearer "):
            return authorization[7:].strip() or None
        value = request.headers.get("x-reghub-token")
        return value.strip() if value and value.strip() else None

    @staticmethod
    def _headers(result: RateLimitResult) -> dict[str, str]:
        values = {
            "RateLimit-Limit": str(result.limit),
            "RateLimit-Remaining": str(result.remaining),
            "RateLimit-Reset": str(result.retry_after),
            "X-RateLimit-Limit": str(result.limit),
            "X-RateLimit-Remaining": str(result.remaining),
            "X-RateLimit-Reset": str(result.retry_after),
        }
        if not result.allowed:
            values["Retry-After"] = str(result.retry_after)
        return values

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self.settings.rate_limit_enabled:
            return await call_next(request)
        path = request.url.path
        if path in {"/api/v1/health", "/api/v1/ready"}:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        checks: list[tuple[str, str, int]] = []
        if path.startswith("/admin") or path.startswith("/auth"):
            cookie = request.cookies.get("reghub_auth")
            checks.append(
                (
                    "admin",
                    cookie or client_ip,
                    self.settings.rate_limit_admin_per_minute,
                )
            )
        elif path.startswith("/api/v1"):
            credential = self._credential(request)
            if credential:
                # A token gets its own high-throughput quota, while a broader per-IP ceiling
                # prevents an attacker from bypassing limits by rotating random token strings.
                checks.extend(
                    [
                        ("token", credential, self.settings.rate_limit_token_per_minute),
                        (
                            "token-ip",
                            client_ip,
                            self.settings.rate_limit_token_ip_per_minute,
                        ),
                    ]
                )
            else:
                checks.append(("public", client_ip, self.settings.rate_limit_public_per_minute))
        else:
            return await call_next(request)

        results = [
            await self.service.check(bucket, identifier, limit)
            for bucket, identifier, limit in checks
        ]
        failed = next((item for item in results if not item.allowed), None)
        effective = failed or min(results, key=lambda item: item.remaining)
        headers = self._headers(effective)
        if failed is not None:
            request_id = getattr(request.state, "request_id", None)
            return JSONResponse(
                {
                    "error": {
                        "type": "RateLimitExceeded",
                        "message": "Too many requests. Retry after the indicated delay.",
                        "request_id": request_id,
                    }
                },
                status_code=429,
                headers=headers,
            )
        response = await call_next(request)
        for key, value in headers.items():
            response.headers.setdefault(key, value)
        return response
