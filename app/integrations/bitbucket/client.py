import json
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from app.core.exceptions import ExternalServiceError, NotFoundError, ValidationError

_MAX_FILE_BYTES = 512 * 1024


@dataclass(frozen=True, slots=True)
class BitbucketRepositoryData:
    external_id: str
    name: str
    description: str | None
    web_url: str
    default_branch: str
    language: str | None
    stars_count: int
    forks_count: int
    root_files: frozenset[str]
    package_json: dict[str, Any] | None
    source_revision: str | None
    source_updated_at: datetime | None
    files: dict[str, str | None]
    screenshot_urls: list[str]
    raw: dict[str, Any]


class BitbucketClient:
    def __init__(self, username: str | None, app_password: str | None, timeout: int) -> None:
        auth = None
        if username and app_password:
            auth = (username.strip(), app_password.strip())
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"Accept": "application/json"},
            auth=auth,
            follow_redirects=False,
        )
        self.is_authenticated = auth is not None

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, url: str) -> httpx.Response:
        response = await self._client.get(url)
        if response.status_code == 404:
            raise NotFoundError("Bitbucket repository was not found or is not accessible")
        if response.status_code in {401, 403}:
            raise ExternalServiceError(
                "Bitbucket rejected the configured app password or repository access"
            )
        if response.status_code == 429:
            raise ExternalServiceError("Bitbucket API rate limit was reached")
        if response.status_code >= 400:
            raise ExternalServiceError(
                f"Bitbucket API request failed with HTTP {response.status_code}"
            )
        return response

    async def _read_file(self, workspace: str, slug: str, branch: str, path: str) -> str | None:
        encoded_branch = quote(branch, safe="")
        encoded_path = quote(path, safe="/")
        url = (
            f"https://api.bitbucket.org/2.0/repositories/{workspace}/{slug}/src/"
            f"{encoded_branch}/{encoded_path}"
        )
        response = await self._client.get(url)
        if response.status_code == 404:
            return None
        if response.status_code >= 400 or len(response.content) > _MAX_FILE_BYTES:
            return None
        try:
            return response.text
        except UnicodeDecodeError:
            return None

    async def fetch_repository(self, workspace: str, slug: str) -> BitbucketRepositoryData:
        response = await self._request(
            f"https://api.bitbucket.org/2.0/repositories/{workspace}/{slug}"
        )
        data = response.json()
        if data.get("is_private") and not self.is_authenticated:
            raise ValidationError("Private Bitbucket repositories require credentials")
        branch = ((data.get("mainbranch") or {}).get("name")) or "main"
        encoded_branch = quote(branch, safe="")
        source = await self._request(
            f"https://api.bitbucket.org/2.0/repositories/{workspace}/{slug}/src/{encoded_branch}"
        )
        values = source.json().get("values", [])
        root_files = frozenset(
            str(item.get("path", "")).split("/")[-1].casefold() for item in values
        )
        candidates = {
            "readme": ("README.md", "README.rst", "README.txt"),
            "package_json": ("package.json",),
            "requirements": ("requirements.txt",),
            "pyproject": ("pyproject.toml",),
            "dockerfile": ("Dockerfile", "dockerfile"),
            "env_example": (".env.example", ".env.sample", "env.example"),
            "license": ("LICENSE", "LICENSE.md", "COPYING"),
        }
        files: dict[str, str | None] = {}
        for key, names in candidates.items():
            files[key] = None
            for name in names:
                if name.casefold() in root_files:
                    files[key] = await self._read_file(workspace, slug, branch, name)
                    if files[key] is not None:
                        break
        package_json = None
        if files["package_json"]:
            try:
                parsed = json.loads(files["package_json"] or "")
                package_json = parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                pass
        screenshots: list[str] = []
        for directory in ("screenshots", "docs", "public", "assets"):
            folder = await self._client.get(
                f"https://api.bitbucket.org/2.0/repositories/{workspace}/{slug}/src/"
                f"{encoded_branch}/{directory}"
            )
            if folder.status_code != 200:
                continue
            for item in folder.json().get("values", []):
                name = str(item.get("path", "")).casefold()
                if name.endswith((".png", ".jpg", ".jpeg", ".webp")):
                    screenshots.append(
                        f"https://bitbucket.org/{workspace}/{slug}/raw/{branch}/{item['path']}"
                    )
                if len(screenshots) >= 12:
                    break
        updated = None
        if data.get("updated_on"):
            with suppress(ValueError):
                updated = datetime.fromisoformat(str(data["updated_on"]).replace("Z", "+00:00"))
        return BitbucketRepositoryData(
            external_id=str(data.get("uuid") or f"{workspace}/{slug}"),
            name=str(data.get("name") or slug),
            description=data.get("description"),
            web_url=str(
                (data.get("links") or {}).get("html", {}).get("href")
                or f"https://bitbucket.org/{workspace}/{slug}"
            ).rstrip("/"),
            default_branch=branch,
            language=data.get("language") or None,
            stars_count=0,
            forks_count=int(data.get("forks", {}).get("size") or 0),
            root_files=root_files,
            package_json=package_json,
            source_revision=data.get("updated_on"),
            source_updated_at=updated,
            files=files,
            screenshot_urls=screenshots,
            raw={
                "full_name": data.get("full_name"),
                "bitbucket_authenticated": self.is_authenticated,
            },
        )
