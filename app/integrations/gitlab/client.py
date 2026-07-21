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
class GitLabRepositoryData:
    external_id: str
    name: str
    description: str | None
    web_url: str
    default_branch: str
    homepage: str | None
    topics: list[str]
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


class GitLabClient:
    def __init__(self, token: str | None, timeout: int) -> None:
        headers = {"Accept": "application/json"}
        if token:
            headers["PRIVATE-TOKEN"] = token.strip()
        self._client = httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=False)
        self.is_authenticated = bool(token and token.strip())

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, url: str, *, params: dict[str, str] | None = None) -> httpx.Response:
        response = await self._client.get(url, params=params)
        if response.status_code == 404:
            raise NotFoundError("GitLab repository was not found or is not accessible")
        if response.status_code in {401, 403}:
            raise ExternalServiceError("GitLab rejected GITLAB_TOKEN or repository access")
        if response.status_code == 429:
            raise ExternalServiceError("GitLab API rate limit was reached")
        if response.status_code >= 400:
            raise ExternalServiceError(
                f"GitLab API request failed with HTTP {response.status_code}"
            )
        return response

    async def _read_file(self, project_id: str, path: str, branch: str) -> str | None:
        encoded_path = quote(path, safe="")
        url = f"https://gitlab.com/api/v4/projects/{project_id}/repository/files/{encoded_path}/raw"
        response = await self._client.get(url, params={"ref": branch})
        if response.status_code == 404:
            return None
        if response.status_code >= 400 or len(response.content) > _MAX_FILE_BYTES:
            return None
        try:
            return response.text
        except UnicodeDecodeError:
            return None

    async def fetch_repository(self, project_path: str) -> GitLabRepositoryData:
        project_id = quote(project_path, safe="")
        response = await self._request(f"https://gitlab.com/api/v4/projects/{project_id}")
        data = response.json()
        if data.get("archived"):
            raise ValidationError("Archived GitLab repositories cannot be imported")
        branch = data.get("default_branch") or "main"
        tree_response = await self._request(
            f"https://gitlab.com/api/v4/projects/{project_id}/repository/tree",
            params={"ref": branch, "per_page": "100"},
        )
        tree = tree_response.json()
        root_files = frozenset(
            str(item.get("name", "")).casefold() for item in tree if item.get("name")
        )
        paths = {
            "readme": ("README.md", "README.rst", "README.txt"),
            "package_json": ("package.json",),
            "requirements": ("requirements.txt",),
            "pyproject": ("pyproject.toml",),
            "dockerfile": ("Dockerfile", "dockerfile"),
            "env_example": (".env.example", ".env.sample", "env.example"),
            "license": ("LICENSE", "LICENSE.md", "COPYING"),
        }
        files: dict[str, str | None] = {}
        for key, candidates in paths.items():
            files[key] = None
            for candidate in candidates:
                if candidate.casefold() in root_files:
                    files[key] = await self._read_file(project_id, candidate, branch)
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
            directory_response = await self._client.get(
                f"https://gitlab.com/api/v4/projects/{project_id}/repository/tree",
                params={"ref": branch, "path": directory, "per_page": "100"},
            )
            if directory_response.status_code != 200:
                continue
            for item in directory_response.json():
                name = str(item.get("name", "")).casefold()
                if name.endswith((".png", ".jpg", ".jpeg", ".webp")):
                    raw_url = f"https://gitlab.com/{project_path}/-/raw/{branch}/{directory}/{item['name']}"
                    screenshots.append(raw_url)
                if len(screenshots) >= 12:
                    break
        updated = None
        raw_updated = data.get("last_activity_at")
        if raw_updated:
            with suppress(ValueError):
                updated = datetime.fromisoformat(str(raw_updated).replace("Z", "+00:00"))
        languages = await self._client.get(
            f"https://gitlab.com/api/v4/projects/{project_id}/languages"
        )
        language = None
        if languages.status_code == 200 and isinstance(languages.json(), dict) and languages.json():
            language = max(languages.json(), key=languages.json().get)
        return GitLabRepositoryData(
            external_id=str(data["id"]),
            name=str(data["name"]),
            description=data.get("description"),
            web_url=str(data["web_url"]).rstrip("/"),
            default_branch=branch,
            homepage=None,
            topics=sorted(
                {str(x).casefold() for x in (data.get("topics") or data.get("tag_list") or [])}
            ),
            language=language,
            stars_count=int(data.get("star_count") or 0),
            forks_count=int(data.get("forks_count") or 0),
            root_files=root_files,
            package_json=package_json,
            source_revision=data.get("last_activity_at"),
            source_updated_at=updated,
            files=files,
            screenshot_urls=screenshots,
            raw={
                "path_with_namespace": data.get("path_with_namespace"),
                "gitlab_authenticated": self.is_authenticated,
            },
        )
