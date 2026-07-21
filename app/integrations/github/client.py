import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from github import Auth, Github
from github.GithubException import (
    BadCredentialsException,
    GithubException,
    RateLimitExceededException,
    UnknownObjectException,
)

from app.core.exceptions import ExternalServiceError, NotFoundError, ValidationError

_MAX_METADATA_FILE_BYTES = 256 * 1024
_MAX_README_BYTES = 768 * 1024
_SCREENSHOT_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


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
    def _screenshots(repo: Any) -> list[str]:
        urls: list[str] = []
        for directory in ("screenshots", "docs", "public", "assets"):
            try:
                items = repo.get_contents(directory)
            except GithubException:
                continue
            if not isinstance(items, list):
                continue
            for item in items[:100]:
                name = str(getattr(item, "name", "")).casefold()
                if name.endswith(_SCREENSHOT_EXTENSIONS):
                    url = getattr(item, "download_url", None)
                    if isinstance(url, str) and url.startswith("https://"):
                        urls.append(url)
                if len(urls) >= 12:
                    return urls
        return urls

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
                branch = repo.get_branch(repo.default_branch or "main")
                source_revision = branch.commit.sha
            except GithubException:
                pass

            return GitHubRepositoryData(
                external_id=str(repo.id),
                name=repo.name,
                full_name=repo.full_name,
                description=repo.description,
                html_url=repo.html_url.rstrip("/"),
                default_branch=repo.default_branch or "main",
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
                screenshot_urls=self._screenshots(repo),
                raw={
                    "full_name": repo.full_name,
                    "owner": repo.owner.login,
                    "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
                    "pushed_at": repo.pushed_at.isoformat() if repo.pushed_at else None,
                    "source_revision": source_revision,
                    "github_authenticated": self._is_authenticated,
                    "package_json_detected": package_json is not None,
                    "readme_detected": bool(readme_text),
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
