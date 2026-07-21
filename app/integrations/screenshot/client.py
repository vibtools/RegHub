import logging

import httpx

logger = logging.getLogger(__name__)


class ScreenshotService:
    """Calls an isolated external screenshot service; RegHub never executes templates."""

    def __init__(self, url: str | None, token: str | None, timeout: int = 45) -> None:
        self._url = (url or "").strip()
        self._token = token
        self._timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self._url)

    async def generate(self, preview_url: str) -> str | None:
        if not self.enabled or not preview_url.startswith("https://"):
            return None
        headers = {"Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False) as client:
                response = await client.post(self._url, headers=headers, json={"url": preview_url})
                response.raise_for_status()
                value = response.json().get("screenshot_url")
                return value if isinstance(value, str) and value.startswith("https://") else None
        except Exception:
            logger.exception("External screenshot generation failed")
            return None
