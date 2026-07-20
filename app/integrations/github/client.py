import json
from dataclasses import dataclass
from typing import Any

from github import Auth, Github
from github.GithubException import (
    BadCredentialsException,
    GithubException,
    RateLimitExceededException,
    UnknownObjectException,
)

from app.core.exceptions import ExternalServiceError, NotFoundError, ValidationError

_MAX_PACKAGE_JSON_BYTES = 256 * 1024


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
    raw: dict[str, Any]


class GitHubClient:
    """Read-only GitHub metadata client.

    A fine-grained PAT can be supplied through ``GITHUB_TOKEN``. The token is only
    passed to PyGithub and is never returned in metadata or logs.
    """

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
    def _read_package_json(repo: Any) -> dict[str, Any] | None:
        """Read a small root package.json through the GitHub Contents API.

        No repository clone, checkout, install, build, or code execution occurs.
        Invalid or oversized files are ignored and normal metadata import continues.
        """

        try:
            content = repo.get_contents("package.json")
            if isinstance(content, list) or getattr(content, "type", "file") != "file":
                return None
            size = int(getattr(content, "size", 0) or 0)
            if size <= 0 or size > _MAX_PACKAGE_JSON_BYTES:
                return None
            decoded = content.decoded_content
            if not isinstance(decoded, bytes) or len(decoded) > _MAX_PACKAGE_JSON_BYTES:
                return None
            parsed = json.loads(decoded.decode("utf-8"))
            return parsed if isinstance(parsed, dict) else None
        except (UnicodeDecodeError, json.JSONDecodeError, GithubException):
            return None

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

            license_spdx = None
            try:
                license_info = repo.get_license()
                license_spdx = getattr(license_info.license, "spdx_id", None)
            except UnknownObjectException:
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
                raw={
                    "full_name": repo.full_name,
                    "owner": repo.owner.login,
                    "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
                    "pushed_at": repo.pushed_at.isoformat() if repo.pushed_at else None,
                    "github_authenticated": self._is_authenticated,
                    "package_json_detected": package_json is not None,
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
