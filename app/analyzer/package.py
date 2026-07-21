import re
from typing import Any

_VERSION_RE = re.compile(r"(?P<version>\d+(?:\.\d+){0,2})")


def package_names(package_json: dict[str, Any] | None) -> set[str]:
    if not isinstance(package_json, dict):
        return set()
    names: set[str] = set()
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        values = package_json.get(section)
        if isinstance(values, dict):
            names.update(str(name).casefold() for name in values)
    return names


def package_version(package_json: dict[str, Any] | None, package_name: str) -> str | None:
    if not isinstance(package_json, dict):
        return None
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        values = package_json.get(section)
        if not isinstance(values, dict):
            continue
        raw = values.get(package_name)
        if raw is None:
            continue
        match = _VERSION_RE.search(str(raw))
        return match.group("version") if match else str(raw)[:50]
    return None


def detect_package_manager(root_files: frozenset[str]) -> str | None:
    files = {name.casefold() for name in root_files}
    if "pnpm-lock.yaml" in files:
        return "pnpm"
    if "yarn.lock" in files:
        return "yarn"
    if "bun.lockb" in files or "bun.lock" in files:
        return "bun"
    if "package-lock.json" in files or "package.json" in files:
        return "npm"
    if "poetry.lock" in files:
        return "poetry"
    if "uv.lock" in files:
        return "uv"
    if "pipfile.lock" in files:
        return "pipenv"
    if "requirements.txt" in files or "pyproject.toml" in files:
        return "pip"
    if "composer.lock" in files or "composer.json" in files:
        return "composer"
    return None


def detect_commands(
    package_json: dict[str, Any] | None,
    package_manager: str | None,
    framework_slug: str,
) -> tuple[str | None, str | None]:
    scripts = package_json.get("scripts", {}) if isinstance(package_json, dict) else {}
    if not isinstance(scripts, dict):
        scripts = {}
    prefix = package_manager or "npm"
    runner = {
        "npm": "npm run",
        "pnpm": "pnpm",
        "yarn": "yarn",
        "bun": "bun run",
    }.get(prefix, "npm run")

    build = f"{runner} build" if "build" in scripts else None
    start = None
    for candidate in ("start", "preview", "dev"):
        if candidate in scripts:
            start = f"{runner} {candidate}"
            break

    if framework_slug == "fastapi" and not start:
        start = "uvicorn app.main:app --host 0.0.0.0 --port 8000"
    elif framework_slug == "django" and not start:
        start = "python manage.py runserver 0.0.0.0:8000"
    elif framework_slug == "laravel" and not start:
        start = "php artisan serve --host=0.0.0.0 --port=8000"
    return build, start
