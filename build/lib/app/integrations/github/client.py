import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote

from github import Auth, Github
from github.GithubException import (
    BadCredentialsException,
    GithubException,
    RateLimitExceededException,
    UnknownObjectException,
)

from app.analyzer.media import (
    extract_readme_image_references,
    is_probable_template_image,
    is_readme_media_candidate,
    merge_media_urls,
    normalize_media_urls,
)
from app.core.exceptions import ExternalServiceError, NotFoundError, ValidationError

_MAX_METADATA_FILE_BYTES = 256 * 1024
_MAX_README_BYTES = 768 * 1024
_MAX_TREE_ENTRIES = 2500
_MAX_SCREENSHOTS = 20


@dataclass(frozen=True, slots=True)
class GitHubRepositoryData:
    external_id: str
    name: str
    full_name: str
    description: str | None
    html_url: str
    default_branch: str
    homepage: str | None
    license_spdx: str | None
    topics: list[str]
    language: str | None
    stars_count: int
    forks_count: int
    private: bool
    archived: bool
    root_files: frozenset[str]
    package_json: dict[str, Any] | None
    source_revision: str | None
    source_updated_at: datetime | None
    readme_text: str | None
    requirements_text: str | None
    pyproject_text: str | None
    dockerfile_text: str | None
    env_example_text: str | None
    license_text: str | None
    screenshot_urls: list[str]
    owner_login: str | None
    owner_name: str | None
    owner_type: str | None
    owner_url: str | None
    raw: dict[str, Any]


class GitHubClient:
    """Read-only GitHub metadata client. No repository code is executed."""

    def __init__(self, token: str | None, timeout: int, allow_private: bool) -> None:
        normalized_token = token.strip() if token else None
        auth = Auth.Token(normalized_token) if normalized_token else None
        self._client = Github(auth=auth, timeout=timeout, per_page=100)
        self._allow_private = allow_private
        self._is_authenticated = bool(normalized_token)

    @property
    def is_authenticated(self) -> bool:
        return self._is_authenticated

    @staticmethod
    def _read_text(repo: Any, path: str, limit: int = _MAX_METADATA_FILE_BYTES) -> str | None:
        try:
            content = repo.get_contents(path)
            if isinstance(content, list) or getattr(content, "type", "file") != "file":
                return None
            size = int(getattr(content, "size", 0) or 0)
            if size <= 0 or size > limit:
                return None
            decoded = content.decoded_content
            if not isinstance(decoded, bytes) or len(decoded) > limit:
                return None
            return decoded.decode("utf-8")
        except (UnicodeDecodeError, GithubException):
            return None

    @classmethod
    def _read_package_json(cls, repo: Any) -> dict[str, Any] | None:
        text = cls._read_text(repo, "package.json")
        if text is None:
            return None
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None

    @classmethod
    def _read_first(
        cls, repo: Any, candidates: tuple[str, ...], limit: int = _MAX_METADATA_FILE_BYTES
    ) -> str | None:
        for path in candidates:
            value = cls._read_text(repo, path, limit)
            if value is not None:
                return value
        return None

    @staticmethod
    def _raw_url(full_name: str, branch: str, path: str) -> str:
        encoded_path = "/".join(quote(part, safe="") for part in path.lstrip("./").split("/"))
        encoded_branch = quote(branch, safe="")
        return f"https://raw.githubusercontent.com/{full_name}/{encoded_branch}/{encoded_path}"

    @classmethod
    def _screenshots(
        cls,
        repo: Any,
        *,
        full_name: str,
        branch: str,
        source_revision: str | None,
        readme_text: str | None,
    ) -> list[str]:
        tree_urls: list[str] = []
        try:
            tree_ref = source_revision or branch
            tree = repo.get_git_tree(tree_ref, recursive=True)
            for item in list(getattr(tree, "tree", []) or [])[:_MAX_TREE_ENTRIES]:
                path = str(getattr(item, "path", "") or "")
                if getattr(item, "type", None) == "blob" and is_probable_template_image(path):
                    tree_urls.append(cls._raw_url(full_name, branch, path))
                    if len(tree_urls) >= _MAX_SCREENSHOTS:
                        break
        except GithubException:
            # Fall back to a bounded list of common folders for providers that restrict tree access.
            for directory in ("screenshots", "docs", "public", "assets", "images", "src/assets"):
                try:
                    items = repo.get_contents(directory)
                except GithubException:
                    continue
                if not isinstance(items, list):
                    continue
                for item in items[:100]:
                    path = str(getattr(item, "path", "") or "")
                    if is_probable_template_image(path):
                        url = getattr(item, "download_url", None)
                        if isinstance(url, str) and url.startswith("https://"):
                            tree_urls.append(url)
                    if len(tree_urls) >= _MAX_SCREENSHOTS:
                        break

        readme_refs = [
            ref
            for ref in extract_readme_image_references(readme_text)
            if is_readme_media_candidate(ref)
        ]
        readme_urls = normalize_media_urls(
            readme_refs,
            relative_resolver=lambda path: cls._raw_url(full_name, branch, path),
            limit=_MAX_SCREENSHOTS,
        )
        return merge_media_urls(readme_urls, tree_urls, limit=_MAX_SCREENSHOTS)

    def fetch_repository(self, owner: str, repository: str) -> GitHubRepositoryData:
        try:
            repo = self._client.get_repo(f"{owner}/{repository}")
            if repo.private and not self._allow_private:
                raise ValidationError("Private GitHub repositories are disabled for this registry")
            if repo.archived:
                raise ValidationError("Archived GitHub repositories cannot be imported")

            try:
                root_files = frozenset(item.name.casefold() for item in repo.get_contents(""))
            except GithubException:
                root_files = frozenset()

            package_json = self._read_package_json(repo) if "package.json" in root_files else None
            readme_text = None
            try:
                readme = repo.get_readme()
                if int(getattr(readme, "size", 0) or 0) <= _MAX_README_BYTES:
                    readme_text = readme.decoded_content.decode("utf-8")
            except (UnknownObjectException, UnicodeDecodeError):
                pass

            license_spdx = None
            license_text = None
            try:
                license_info = repo.get_license()
                license_spdx = getattr(license_info.license, "spdx_id", None)
                content = getattr(license_info, "decoded_content", None)
                if isinstance(content, bytes) and len(content) <= _MAX_METADATA_FILE_BYTES:
                    license_text = content.decode("utf-8", errors="replace")
            except UnknownObjectException:
                pass

            source_revision = None
            try:
                branch_info = repo.get_branch(repo.default_branch or "main")
                source_revision = branch_info.commit.sha
            except GithubException:
                pass

            owner_object = repo.owner
            owner_login = getattr(owner_object, "login", None)
            owner_name = getattr(owner_object, "name", None) or owner_login
            owner_type = getattr(owner_object, "type", None)
            owner_url = getattr(owner_object, "html_url", None)
            branch = repo.default_branch or "main"
            screenshots = self._screenshots(
                repo,
                full_name=repo.full_name,
                branch=branch,
                source_revision=source_revision,
                readme_text=readme_text,
            )

            return GitHubRepositoryData(
                external_id=str(repo.id),
                name=repo.name,
                full_name=repo.full_name,
                description=repo.description,
                html_url=repo.html_url.rstrip("/"),
                default_branch=branch,
                homepage=repo.homepage or None,
                license_spdx=license_spdx,
                topics=sorted({topic.casefold() for topic in repo.get_topics()}),
                language=repo.language,
                stars_count=repo.stargazers_count,
                forks_count=repo.forks_count,
                private=repo.private,
                archived=repo.archived,
                root_files=root_files,
                package_json=package_json,
                source_revision=source_revision,
                source_updated_at=repo.pushed_at or repo.updated_at,
                readme_text=readme_text,
                requirements_text=self._read_first(repo, ("requirements.txt",)),
                pyproject_text=self._read_first(repo, ("pyproject.toml",)),
                dockerfile_text=self._read_first(repo, ("Dockerfile", "dockerfile")),
                env_example_text=self._read_first(
                    repo, (".env.example", ".env.sample", "env.example")
                ),
                license_text=license_text,
                screenshot_urls=screenshots,
                owner_login=owner_login,
                owner_name=owner_name,
                owner_type=owner_type,
                owner_url=owner_url,
                raw={
                    "full_name": repo.full_name,
                    "owner": owner_login,
                    "owner_name": owner_name,
                    "owner_type": owner_type,
                    "owner_url": owner_url,
                    "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
                    "pushed_at": repo.pushed_at.isoformat() if repo.pushed_at else None,
                    "source_revision": source_revision,
                    "github_authenticated": self._is_authenticated,
                    "package_json_detected": package_json is not None,
                    "readme_detected": bool(readme_text),
                    "screenshot_count": len(screenshots),
                },
            )
        except BadCredentialsException as exc:
            raise ExternalServiceError(
                "GitHub rejected GITHUB_TOKEN. Replace or remove the token and redeploy."
            ) from exc
        except RateLimitExceededException as exc:
            raise ExternalServiceError(
                "GitHub API rate limit was reached. Configure a valid GITHUB_TOKEN or retry later."
            ) from exc
        except UnknownObjectException as exc:
            raise NotFoundError("GitHub repository was not found or is not accessible") from exc
        except ValidationError:
            raise
        except GithubException as exc:
            message = exc.data.get("message") if isinstance(exc.data, dict) else str(exc)
            raise ExternalServiceError(f"GitHub API request failed: {message}") from exc
