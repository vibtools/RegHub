from dataclasses import dataclass
from typing import Any

from github import Auth, Github
from github.GithubException import GithubException, UnknownObjectException

from app.core.exceptions import ExternalServiceError, NotFoundError, ValidationError


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
    raw: dict[str, Any]


class GitHubClient:
    def __init__(self, token: str | None, timeout: int, allow_private: bool) -> None:
        auth = Auth.Token(token) if token else None
        self._client = Github(auth=auth, timeout=timeout, per_page=100)
        self._allow_private = allow_private

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
                raw={
                    "full_name": repo.full_name,
                    "owner": repo.owner.login,
                    "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
                    "pushed_at": repo.pushed_at.isoformat() if repo.pushed_at else None,
                },
            )
        except UnknownObjectException as exc:
            raise NotFoundError("GitHub repository was not found or is not accessible") from exc
        except ValidationError:
            raise
        except GithubException as exc:
            message = exc.data.get("message") if isinstance(exc.data, dict) else str(exc)
            raise ExternalServiceError(f"GitHub API request failed: {message}") from exc
