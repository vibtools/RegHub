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
class BitbucketRepositoryData:
    external_id: str
    name: str
    description: str | None
    web_url: str
    default_branch: str
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

    async def _request(self, url: str, *, params: dict[str, str] | None = None) -> httpx.Response:
        response = await self._client.get(url, params=params)
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

    @staticmethod
    def _raw_url(workspace: str, slug: str, branch: str, path: str) -> str:
        encoded_branch = quote(branch, safe="")
        clean_path = path.lstrip("./")
        return f"https://bitbucket.org/{workspace}/{slug}/raw/{encoded_branch}/{clean_path}"

    async def _recursive_paths(self, workspace: str, slug: str, branch: str) -> list[str]:
        encoded_branch = quote(branch, safe="")
        queue: list[tuple[str, int]] = [("", 0)]
        seen_directories: set[str] = set()
        result: list[str] = []
        requests = 0
        while queue and len(result) < _MAX_TREE_ENTRIES and requests < 120:
            directory, depth = queue.pop(0)
            if directory in seen_directories or depth > 6:
                continue
            seen_directories.add(directory)
            encoded_path = quote(directory, safe="/")
            base = (
                f"https://api.bitbucket.org/2.0/repositories/{workspace}/{slug}/src/"
                f"{encoded_branch}"
            )
            url: str | None = f"{base}/{encoded_path}" if encoded_path else base
            page = 0
            while url and page < 10 and requests < 120:
                response = await self._client.get(
                    url, params={"pagelen": "100"} if page == 0 else None
                )
                requests += 1
                if response.status_code != 200:
                    break
                payload = response.json()
                for item in payload.get("values", []):
                    path = str(item.get("path") or "")
                    item_type = item.get("type")
                    if item_type == "commit_file" and path:
                        result.append(path)
                        if len(result) >= _MAX_TREE_ENTRIES:
                            break
                    elif item_type == "commit_directory" and path and depth < 6:
                        queue.append((path, depth + 1))
                url = payload.get("next")
                page += 1
        return result

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

        tree_paths = await self._recursive_paths(workspace, slug, branch)
        tree_urls = [
            self._raw_url(workspace, slug, branch, path)
            for path in tree_paths
            if is_probable_template_image(path)
        ][:_MAX_SCREENSHOTS]
        readme_urls = normalize_media_urls(
            [
                ref
                for ref in extract_readme_image_references(files.get("readme"))
                if is_readme_media_candidate(ref)
            ],
            relative_resolver=lambda path: self._raw_url(workspace, slug, branch, path),
            limit=_MAX_SCREENSHOTS,
        )
        screenshots = merge_media_urls(readme_urls, tree_urls, limit=_MAX_SCREENSHOTS)

        updated = None
        if data.get("updated_on"):
            with suppress(ValueError):
                updated = datetime.fromisoformat(str(data["updated_on"]).replace("Z", "+00:00"))
        owner = data.get("owner") or data.get("workspace") or {}
        owner_login = str(owner.get("nickname") or owner.get("slug") or workspace)
        owner_name = str(owner.get("display_name") or owner.get("name") or owner_login)
        owner_type = "Organization" if data.get("workspace") else "User"
        owner_url = (owner.get("links") or {}).get("html", {}).get(
            "href"
        ) or f"https://bitbucket.org/{workspace}"
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
            private=bool(data.get("is_private")),
            root_files=root_files,
            package_json=package_json,
            source_revision=data.get("updated_on"),
            source_updated_at=updated,
            files=files,
            screenshot_urls=screenshots,
            owner_login=owner_login,
            owner_name=owner_name,
            owner_type=owner_type,
            owner_url=str(owner_url),
            raw={
                "full_name": data.get("full_name"),
                "owner": owner_login,
                "owner_name": owner_name,
                "owner_type": owner_type,
                "owner_url": owner_url,
                "bitbucket_authenticated": self.is_authenticated,
                "private": bool(data.get("is_private")),
                "screenshot_count": len(screenshots),
            },
        )
