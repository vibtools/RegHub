import logging
from typing import Any

import httpx

from app import __version__
from app.core.exceptions import ExternalServiceError, ValidationError
from app.core.url_security import validate_public_https_url

logger = logging.getLogger(__name__)

_MAX_RESPONSE_BYTES = 1_000_000


class ScreenshotService:
    """Calls an isolated external screenshot service; RegHub never executes templates."""

    def __init__(self, url: str | None, token: str | None, timeout: int = 45) -> None:
        self._url = (url or "").strip()
        self._token = token
        self._timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self._url)

    async def generate_with_metadata(self, preview_url: str) -> tuple[str, dict[str, Any]]:
        if not self.enabled:
            raise ValidationError("SCREENSHOT_SERVICE_URL is not configured")
        validated_preview = validate_public_https_url(preview_url, field_name="Preview URL")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": f"RegHub-Screenshot-Client/{__version__}",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False) as client:
                response = await client.post(
                    self._url,
                    headers=headers,
                    json={"url": validated_preview, "format": "webp", "full_page": True},
                )
                response.raise_for_status()
                if len(response.content) > _MAX_RESPONSE_BYTES:
                    raise ExternalServiceError("Screenshot service response was too large")
                payload = response.json()
                value = payload.get("screenshot_url")
                if not isinstance(value, str):
                    raise ExternalServiceError("Screenshot service returned no screenshot_url")
                screenshot_url = validate_public_https_url(value, field_name="Screenshot URL")
                safe_metadata = {
                    "status_code": response.status_code,
                    "provider_request_id": response.headers.get("x-request-id"),
                    "width": payload.get("width"),
                    "height": payload.get("height"),
                    "format": payload.get("format"),
                }
                return screenshot_url, safe_metadata
        except ValidationError:
            raise
        except httpx.TimeoutException as exc:
            raise ExternalServiceError("Screenshot service timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise ExternalServiceError(
                f"Screenshot service returned HTTP {exc.response.status_code}"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ExternalServiceError("Screenshot service request failed") from exc

    async def generate(self, preview_url: str) -> str | None:
        try:
            value, _ = await self.generate_with_metadata(preview_url)
            return value
        except Exception:
            logger.exception("External screenshot generation failed")
            return None
