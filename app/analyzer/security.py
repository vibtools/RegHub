import re

from app.registry.adapters.base import ImportedRepository

_SECRET_PATTERN = re.compile(
    r"(?im)^\s*(?:[A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|PRIVATE_KEY)[A-Z0-9_]*)\s*=\s*([^#\r\n]+)"
)


def inspect_security(repository: ImportedRepository) -> list[str]:
    signals: list[str] = []
    files = {name.casefold() for name in repository.root_files}
    if ".env" in files:
        signals.append("Repository contains a root .env file; verify that it contains no secrets")
    env_text = repository.env_example_text or ""
    for match in _SECRET_PATTERN.finditer(env_text):
        value = match.group(1).strip().strip("\"'")
        if value and value.casefold() not in {
            "change-me",
            "changeme",
            "example",
            "your-token",
            "",
        }:
            signals.append("Environment example may contain a non-placeholder secret value")
            break
    if repository.dockerfile_text and "latest" in repository.dockerfile_text.casefold():
        signals.append("Dockerfile appears to use an unpinned latest image tag")
    if not repository.license_spdx:
        signals.append("No recognized open-source license metadata")
    return signals
