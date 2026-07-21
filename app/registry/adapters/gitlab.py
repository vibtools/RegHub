import re
from urllib.parse import urlsplit

from app.core.exceptions import ValidationError
from app.integrations.gitlab.client import GitLabClient
from app.registry.adapters.base import ImportedRepository, RegistryAdapter

_PART = re.compile(r"^[A-Za-z0-9_.-]+$")


def parse_gitlab_repository_url(url: str) -> tuple[str, str]:
    parsed = urlsplit(url.strip())
    if parsed.scheme != "https" or parsed.hostname not in {"gitlab.com", "www.gitlab.com"}:
        raise ValidationError("GitLab URL must use HTTPS and the gitlab.com host")
    if parsed.query or parsed.fragment or parsed.username or parsed.password or parsed.port:
        raise ValidationError("GitLab URL cannot contain credentials, ports, query, or fragment")
    if "/-/" in parsed.path:
        raise ValidationError("GitLab URL must point to the repository root")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or any(not _PART.fullmatch(part.removesuffix(".git")) for part in parts):
        raise ValidationError("GitLab URL must identify a repository namespace and name")
    parts[-1] = parts[-1].removesuffix(".git")
    path = "/".join(parts)
    return path, f"https://gitlab.com/{path}"


class GitLabRegistryAdapter(RegistryAdapter):
    name = "gitlab"

    def __init__(self, client: GitLabClient) -> None:
        self._client = client

    async def import_repository(self, repository_url: str) -> ImportedRepository:
        path, normalized = parse_gitlab_repository_url(repository_url)
        data = await self._client.fetch_repository(path)
        return ImportedRepository(
            adapter=self.name,
            external_id=f"gitlab:{data.external_id}",
            name=data.name,
            description=data.description,
            repository_url=normalized,
            default_branch=data.default_branch,
            homepage_url=data.homepage,
            license_spdx=None,
            topics=data.topics,
            primary_language=data.language,
            stars_count=data.stars_count,
            forks_count=data.forks_count,
            root_files=data.root_files,
            package_json=data.package_json,
            metadata=data.raw,
            source_revision=data.source_revision,
            source_updated_at=data.source_updated_at,
            readme_text=data.files.get("readme"),
            requirements_text=data.files.get("requirements"),
            pyproject_text=data.files.get("pyproject"),
            dockerfile_text=data.files.get("dockerfile"),
            env_example_text=data.files.get("env_example"),
            license_text=data.files.get("license"),
            screenshot_urls=data.screenshot_urls,
        )
