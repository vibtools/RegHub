from abc import ABC, abstractmethod
from dataclasses import dataclass
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
    metadata: dict[str, Any]


class RegistryAdapter(ABC):
    name: str

    @abstractmethod
    async def import_repository(self, repository_url: str) -> ImportedRepository:
        raise NotImplementedError
