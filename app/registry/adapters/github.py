import asyncio
import re
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from app.core.exceptions import ValidationError
from app.registry.adapters.base import ImportedRepository, RegistryAdapter

if TYPE_CHECKING:
    from app.integrations.github.client import GitHubClient

_GITHUB_PART = re.compile(r"^[A-Za-z0-9_.-]+$")


def parse_github_repository_url(repository_url: str) -> tuple[str, str, str]:
    raw = repository_url.strip()
    parsed = urlsplit(raw)
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"}:
        raise ValidationError("Repository URL must use HTTPS and the github.com host")
    if parsed.query or parsed.fragment or parsed.username or parsed.password or parsed.port:
        raise ValidationError(
            "Repository URL cannot contain credentials, ports, query, or fragment"
        )
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2:
        raise ValidationError(
            "Repository URL must have the form https://github.com/owner/repository"
        )
    owner, repository = parts
    if repository.endswith(".git"):
        repository = repository[:-4]
    if (
        not owner
        or not repository
        or not _GITHUB_PART.fullmatch(owner)
        or not _GITHUB_PART.fullmatch(repository)
    ):
        raise ValidationError("Repository owner or name contains unsupported characters")
    normalized = f"https://github.com/{owner}/{repository}"
    return owner, repository, normalized


class GitHubRegistryAdapter(RegistryAdapter):
    name = "github"

    def __init__(self, client: "GitHubClient") -> None:
        self._client = client

    async def import_repository(self, repository_url: str) -> ImportedRepository:
        owner, repository, normalized = parse_github_repository_url(repository_url)
        data = await asyncio.to_thread(self._client.fetch_repository, owner, repository)
        return ImportedRepository(
            adapter=self.name,
            external_id=data.external_id,
            name=data.name,
            description=data.description,
            repository_url=normalized,
            default_branch=data.default_branch,
            homepage_url=data.homepage,
            license_spdx=data.license_spdx,
            topics=data.topics,
            primary_language=data.language,
            stars_count=data.stars_count,
            forks_count=data.forks_count,
            root_files=data.root_files,
            package_json=data.package_json,
            metadata=data.raw,
            source_revision=data.source_revision,
            source_updated_at=data.source_updated_at,
            readme_text=data.readme_text,
            requirements_text=data.requirements_text,
            pyproject_text=data.pyproject_text,
            dockerfile_text=data.dockerfile_text,
            env_example_text=data.env_example_text,
            license_text=data.license_text,
            screenshot_urls=data.screenshot_urls,
        )
