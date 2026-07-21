from app.core.exceptions import ValidationError
from app.registry.adapters.base import RegistryAdapter


class AdapterRegistry:
    def __init__(self, adapters: list[RegistryAdapter]) -> None:
        self._adapters = {adapter.name: adapter for adapter in adapters}

    @property
    def names(self) -> list[str]:
        return sorted(self._adapters)

    def get(self, name: str) -> RegistryAdapter:
        try:
            return self._adapters[name]
        except KeyError as exc:
            raise ValidationError(f"Unsupported registry adapter: {name}") from exc
