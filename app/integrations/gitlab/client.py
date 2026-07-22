import json
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from app.analyzer.media import (
    extract_readme_image_references,
    is_probable_template_image,
    is_readme_media_candidate,
    merge_media_urls,
    normalize_media_urls,
)
from app.core.exceptions import ExternalServiceError, NotFoundError, ValidationError

_MAX_FILE_BYTES = 512 * 1024
_MAX_TREE_ENTRIES = 2500
_MAX_SCREENSHOTS = 20


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
    private: bool
    root_files: frozenset[str]
    package_json: dict[str, Any] | None
    source_revision: str | None
    source_updated_at: datetime | None
    files: dict[str, str | None]
    screenshot_urls: list[str]
    owner_login: str | None
    owner_name: str | None
    owner_type: str | None
    owner_url: str | None
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

    @staticmethod
    def _raw_url(project_path: str, branch: str, path: str) -> str:
        return (
            f"https://gitlab.com/{project_path}/-/raw/{quote(branch, safe='')}/{path.lstrip('./')}"
        )

    async def _screenshots(
        self,
        *,
        project_id: str,
        project_path: str,
        branch: str,
        readme_text: str | None,
    ) -> list[str]:
        tree_urls: list[str] = []
        scanned = 0
        for page in range(1, 11):
            response = await self._client.get(
                f"https://gitlab.com/api/v4/projects/{project_id}/repository/tree",
                params={
                    "ref": branch,
                    "recursive": "true",
                    "per_page": "100",
                    "page": str(page),
                },
            )
            if response.status_code != 200 or not isinstance(response.json(), list):
                break
            items = response.json()
            for item in items:
                scanned += 1
                if scanned > _MAX_TREE_ENTRIES:
                    break
                path = str(item.get("path") or "")
                if item.get("type") == "blob" and is_probable_template_image(path):
                    tree_urls.append(self._raw_url(project_path, branch, path))
                    if len(tree_urls) >= _MAX_SCREENSHOTS:
                        break
            if len(tree_urls) >= _MAX_SCREENSHOTS or scanned >= _MAX_TREE_ENTRIES:
                break
            if len(items) < 100 and not response.headers.get("x-next-page"):
                break
        readme_urls = normalize_media_urls(
            [
                ref
                for ref in extract_readme_image_references(readme_text)
                if is_readme_media_candidate(ref)
            ],
            relative_resolver=lambda path: self._raw_url(project_path, branch, path),
            limit=_MAX_SCREENSHOTS,
        )
        return merge_media_urls(readme_urls, tree_urls, limit=_MAX_SCREENSHOTS)

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

        namespace = data.get("namespace") or {}
        owner_login = str(namespace.get("path") or project_path.split("/", 1)[0])
        owner_name = str(namespace.get("name") or owner_login)
        namespace_kind = str(namespace.get("kind") or "group").casefold()
        owner_type = "Organization" if namespace_kind == "group" else "User"
        owner_url = namespace.get("web_url") or f"https://gitlab.com/{owner_login}"
        screenshots = await self._screenshots(
            project_id=project_id,
            project_path=project_path,
            branch=branch,
            readme_text=files.get("readme"),
        )
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
            private=str(data.get("visibility") or "private").casefold() != "public",
            root_files=root_files,
            package_json=package_json,
            source_revision=data.get("last_activity_at"),
            source_updated_at=updated,
            files=files,
            screenshot_urls=screenshots,
            owner_login=owner_login,
            owner_name=owner_name,
            owner_type=owner_type,
            owner_url=str(owner_url),
            raw={
                "path_with_namespace": data.get("path_with_namespace"),
                "owner": owner_login,
                "owner_name": owner_name,
                "owner_type": owner_type,
                "owner_url": owner_url,
                "gitlab_authenticated": self.is_authenticated,
                "visibility": str(data.get("visibility") or "private").casefold(),
                "screenshot_count": len(screenshots),
            },
        )
