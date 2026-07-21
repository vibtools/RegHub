import re
from urllib.parse import urlsplit

from app.core.exceptions import ValidationError
from app.integrations.bitbucket.client import BitbucketClient
from app.registry.adapters.base import ImportedRepository, RegistryAdapter

_PART = re.compile(r"^[A-Za-z0-9_.-]+$")


def parse_bitbucket_repository_url(url: str) -> tuple[str, str, str]:
    parsed = urlsplit(url.strip())
    if parsed.scheme != "https" or parsed.hostname not in {"bitbucket.org", "www.bitbucket.org"}:
        raise ValidationError("Bitbucket URL must use HTTPS and the bitbucket.org host")
    if parsed.query or parsed.fragment or parsed.username or parsed.password or parsed.port:
        raise ValidationError("Bitbucket URL cannot contain credentials, ports, query, or fragment")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2:
        raise ValidationError(
            "Bitbucket URL must have the form https://bitbucket.org/workspace/repository"
        )
    workspace, slug = parts
    slug = slug.removesuffix(".git")
    if not _PART.fullmatch(workspace) or not _PART.fullmatch(slug):
        raise ValidationError("Bitbucket workspace or repository contains unsupported characters")
    return workspace, slug, f"https://bitbucket.org/{workspace}/{slug}"


class BitbucketRegistryAdapter(RegistryAdapter):
    name = "bitbucket"

    def __init__(self, client: BitbucketClient) -> None:
        self._client = client

    async def import_repository(self, repository_url: str) -> ImportedRepository:
        workspace, slug, normalized = parse_bitbucket_repository_url(repository_url)
        data = await self._client.fetch_repository(workspace, slug)
        return ImportedRepository(
            adapter=self.name,
            external_id=f"bitbucket:{data.external_id}",
            name=data.name,
            description=data.description,
            repository_url=normalized,
            default_branch=data.default_branch,
            homepage_url=None,
            license_spdx=None,
            topics=[],
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
            owner_login=data.owner_login,
            owner_name=data.owner_name,
            owner_type=data.owner_type,
            owner_url=data.owner_url,
        )
