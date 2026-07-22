import io
import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from app.core.exceptions import ValidationError
from app.core.url_security import validate_public_https_url
from app.registry.adapters.base import ImportedRepository

_MAX_TEXT_FILE = 512 * 1024
_ALLOWED_SCREENSHOT_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


def _safe_member(name: str) -> PurePosixPath:
    if not name or any(ord(character) < 32 for character in name):
        raise ValidationError("ZIP contains an unsafe file path")
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValidationError("ZIP contains an unsafe file path")
    return path


def _read_text(archive: zipfile.ZipFile, member: str | None) -> str | None:
    if not member:
        return None
    info = archive.getinfo(member)
    if info.file_size > _MAX_TEXT_FILE:
        return None
    try:
        return archive.read(member).decode("utf-8")
    except (UnicodeDecodeError, KeyError):
        return None


def _bounded_text(value: object, *, field_name: str, maximum: int) -> str:
    result = str(value or "").strip()
    if any(ord(character) < 32 for character in result):
        raise ValidationError(f"{field_name} contains control characters")
    if len(result) > maximum:
        raise ValidationError(f"{field_name} exceeds {maximum} characters")
    return result


def _optional_https_url(value: object, *, field_name: str) -> str | None:
    candidate = str(value or "").strip()
    if not candidate:
        return None
    return validate_public_https_url(candidate, field_name=field_name)


def _optional_content(value: object, *, field_name: str, maximum: int) -> str | None:
    result = str(value or "").strip()
    if any(ord(character) < 32 and character not in {"\t", "\n", "\r"} for character in result):
        raise ValidationError(f"{field_name} contains unsupported control characters")
    if len(result) > maximum:
        raise ValidationError(f"{field_name} exceeds {maximum} characters")
    return result or None


def repository_from_manifest(payload: dict[str, Any]) -> ImportedRepository:
    name = _bounded_text(payload.get("name"), field_name="Local manifest name", maximum=160)
    repository = _bounded_text(
        payload.get("repository"), field_name="Local manifest repository", maximum=1000
    )
    branch = _bounded_text(
        payload.get("branch") or "main", field_name="Local manifest branch", maximum=255
    )
    if not name:
        raise ValidationError("Local manifest requires a name")
    if repository.startswith("local://"):
        repository_url = repository
    elif repository:
        repository_url = validate_public_https_url(
            repository, field_name="Local manifest repository"
        )
    else:
        repository_url = f"local://manifest/{uuid4()}"

    raw_screenshots = payload.get("screenshots", [])
    if not isinstance(raw_screenshots, list):
        raise ValidationError("Local manifest screenshots must be a list")
    if len(raw_screenshots) > 100:
        raise ValidationError("Local manifest contains too many screenshots")
    screenshots = [
        validate_public_https_url(item, field_name="Local manifest screenshot")
        for item in raw_screenshots[:12]
        if isinstance(item, str)
    ]

    framework = _bounded_text(
        payload.get("framework") or "unknown",
        field_name="Local manifest framework",
        maximum=120,
    ).casefold()
    package_json = (
        payload.get("package_json") if isinstance(payload.get("package_json"), dict) else None
    )
    if package_json is not None and len(json.dumps(package_json)) > _MAX_TEXT_FILE:
        raise ValidationError("Local manifest package_json is too large")
    raw_files = payload.get("files", [])
    if not isinstance(raw_files, list):
        raise ValidationError("Local manifest files must be a list")
    if len(raw_files) > 5000:
        raise ValidationError("Local manifest contains too many files")
    raw_topics = payload.get("topics", [])
    if not isinstance(raw_topics, list):
        raise ValidationError("Local manifest topics must be a list")
    if len(raw_topics) > 200:
        raise ValidationError("Local manifest contains too many topics")
    topics = [
        item.casefold()
        for item in (
            _bounded_text(value, field_name="Local manifest topic", maximum=60)
            for value in raw_topics
            if isinstance(value, str)
        )
        if item
    ][:50]
    if framework != "unknown" and framework not in topics:
        topics.append(framework)

    return ImportedRepository(
        adapter="local-manifest",
        external_id=f"local-manifest:{uuid4()}",
        name=name,
        description=_optional_content(
            payload.get("description"),
            field_name="Local manifest description",
            maximum=5000,
        ),
        repository_url=repository_url,
        default_branch=branch or "main",
        homepage_url=_optional_https_url(
            payload.get("homepage_url"), field_name="Local manifest homepage"
        ),
        license_spdx=(
            _bounded_text(
                payload.get("license_spdx"),
                field_name="Local manifest license",
                maximum=100,
            )
            or None
        ),
        topics=list(dict.fromkeys(topics)),
        primary_language=(
            _bounded_text(
                payload.get("language"),
                field_name="Local manifest language",
                maximum=100,
            )
            or None
        ),
        stars_count=0,
        forks_count=0,
        root_files=frozenset(
            _bounded_text(value, field_name="Local manifest file", maximum=500).casefold()
            for value in raw_files
            if isinstance(value, str)
        ),
        package_json=package_json,
        metadata={"source": "local-manifest", "submitted_at": datetime.now(UTC).isoformat()},
        readme_text=_optional_content(
            payload.get("readme"), field_name="Local manifest README", maximum=200_000
        ),
        requirements_text=_optional_content(
            payload.get("requirements_txt"),
            field_name="Local manifest requirements",
            maximum=_MAX_TEXT_FILE,
        ),
        pyproject_text=_optional_content(
            payload.get("pyproject_toml"),
            field_name="Local manifest pyproject",
            maximum=_MAX_TEXT_FILE,
        ),
        dockerfile_text=_optional_content(
            payload.get("dockerfile"),
            field_name="Local manifest Dockerfile",
            maximum=_MAX_TEXT_FILE,
        ),
        env_example_text=_optional_content(
            payload.get("env_example"),
            field_name="Local manifest env example",
            maximum=_MAX_TEXT_FILE,
        ),
        screenshot_urls=screenshots,
    )


def repository_from_zip(
    data: bytes,
    filename: str,
    *,
    max_uncompressed_bytes: int,
    max_entries: int,
) -> ImportedRepository:
    safe_filename = _bounded_text(
        PurePosixPath(filename.replace("\\", "/")).name,
        field_name="ZIP filename",
        maximum=255,
    )
    if not safe_filename:
        safe_filename = "local-template.zip"

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValidationError("Uploaded file is not a valid ZIP archive") from exc

    with archive:
        infos = archive.infolist()
        if not infos or len(infos) > max_entries:
            raise ValidationError("ZIP contains too many files or is empty")
        total = 0
        safe_names: list[str] = []
        seen_names: set[str] = set()
        for info in infos:
            path = _safe_member(info.filename)
            if info.flag_bits & 0x1:
                raise ValidationError("Encrypted ZIP files are not supported")
            if ((info.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValidationError("ZIP symbolic links are not supported")
            total += info.file_size
            if total > max_uncompressed_bytes:
                raise ValidationError("ZIP uncompressed size exceeds the configured limit")
            if not info.is_dir():
                normalized_name = str(path).casefold()
                if normalized_name in seen_names:
                    raise ValidationError("ZIP contains duplicate or case-colliding file paths")
                seen_names.add(normalized_name)
                safe_names.append(str(path))

        first_parts = {PurePosixPath(name).parts[0] for name in safe_names}
        prefix = (
            next(iter(first_parts)) + "/"
            if len(first_parts) == 1 and all("/" in name for name in safe_names)
            else ""
        )
        logical = {
            name[len(prefix) :].casefold(): name
            for name in safe_names
            if name[len(prefix) :]
        }
        if len(logical) != len(safe_names):
            raise ValidationError("ZIP contains duplicate logical file paths")
        root_files = frozenset(path.split("/", 1)[0] for path in logical)

        def candidate(*names: str) -> str | None:
            for name in names:
                if name.casefold() in logical:
                    return logical[name.casefold()]
            return None

        package_text = _read_text(archive, candidate("package.json"))
        package_json = None
        if package_text:
            try:
                parsed = json.loads(package_text)
                package_json = parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                pass

        encoded_filename = quote(safe_filename, safe="._-")
        screenshots: list[str] = []
        for logical_name in sorted(logical):
            if logical_name.endswith(_ALLOWED_SCREENSHOT_EXTENSIONS) and logical_name.startswith(
                ("screenshots/", "docs/", "public/", "assets/")
            ):
                screenshots.append(f"local-zip://{encoded_filename}/{logical_name}")
            if len(screenshots) >= 12:
                break

        title = re.sub(r"\.zip$", "", safe_filename, flags=re.IGNORECASE).strip()
        title = title or "Local Template"
        return ImportedRepository(
            adapter="local-zip",
            external_id=f"local-zip:{uuid4()}",
            name=title,
            description="Template imported from a validated local ZIP archive.",
            repository_url=f"local://zip/{uuid4()}",
            default_branch="main",
            homepage_url=None,
            license_spdx=None,
            topics=[],
            primary_language=None,
            stars_count=0,
            forks_count=0,
            root_files=root_files,
            package_json=package_json,
            metadata={
                "source": "local-zip",
                "filename": safe_filename,
                "entries": len(infos),
                "uncompressed_bytes": total,
            },
            readme_text=_read_text(archive, candidate("README.md", "README.rst", "README.txt")),
            requirements_text=_read_text(archive, candidate("requirements.txt")),
            pyproject_text=_read_text(archive, candidate("pyproject.toml")),
            dockerfile_text=_read_text(archive, candidate("Dockerfile", "dockerfile")),
            env_example_text=_read_text(
                archive, candidate(".env.example", ".env.sample", "env.example")
            ),
            license_text=_read_text(archive, candidate("LICENSE", "LICENSE.md", "COPYING")),
            screenshot_urls=screenshots,
        )
