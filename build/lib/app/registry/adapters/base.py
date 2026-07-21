from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ImportedRepository:
    adapter: str
    external_id: str
    name: str
    description: str | None
    repository_url: str
    default_branch: str
    homepage_url: str | None
    license_spdx: str | None
    topics: list[str]
    primary_language: str | None
    stars_count: int
    forks_count: int
    root_files: frozenset[str]
    package_json: dict[str, Any] | None
    metadata: dict[str, Any]
    source_revision: str | None = None
    source_updated_at: datetime | None = None
    readme_text: str | None = None
    requirements_text: str | None = None
    pyproject_text: str | None = None
    dockerfile_text: str | None = None
    env_example_text: str | None = None
    license_text: str | None = None
    screenshot_urls: list[str] = field(default_factory=list)
    owner_login: str | None = None
    owner_name: str | None = None
    owner_type: str | None = None
    owner_url: str | None = None


class RegistryAdapter(ABC):
    name: str

    @abstractmethod
    async def import_repository(self, repository_url: str) -> ImportedRepository:
        raise NotImplementedError
