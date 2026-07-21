import io
import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4

from app.core.exceptions import ValidationError
from app.registry.adapters.base import ImportedRepository

_MAX_TEXT_FILE = 512 * 1024
_ALLOWED_SCREENSHOT_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


def _safe_member(name: str) -> PurePosixPath:
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


def repository_from_manifest(payload: dict[str, Any]) -> ImportedRepository:
    name = str(payload.get("name") or "").strip()
    repository = str(payload.get("repository") or "").strip()
    branch = str(payload.get("branch") or "main").strip()
    if not name:
        raise ValidationError("Local manifest requires a name")
    if repository and not repository.startswith(("https://", "local://")):
        raise ValidationError("Local manifest repository must use HTTPS or local://")
    repository_url = repository or f"local://manifest/{uuid4()}"
    framework = str(payload.get("framework") or "unknown").casefold()
    package_json = (
        payload.get("package_json") if isinstance(payload.get("package_json"), dict) else None
    )
    files = payload.get("files") if isinstance(payload.get("files"), list) else []
    screenshots = [
        str(x)
        for x in payload.get("screenshots", [])
        if isinstance(x, str) and x.startswith("https://")
    ][:12]
    return ImportedRepository(
        adapter="local-manifest",
        external_id=f"local-manifest:{uuid4()}",
        name=name,
        description=str(payload.get("description") or "").strip() or None,
        repository_url=repository_url,
        default_branch=branch or "main",
        homepage_url=str(payload.get("homepage_url") or "").strip() or None,
        license_spdx=str(payload.get("license_spdx") or "").strip() or None,
        topics=[str(x).casefold() for x in payload.get("topics", []) if isinstance(x, str)][:50]
        + ([framework] if framework != "unknown" else []),
        primary_language=str(payload.get("language") or "").strip() or None,
        stars_count=0,
        forks_count=0,
        root_files=frozenset(str(x).casefold() for x in files),
        package_json=package_json,
        metadata={"source": "local-manifest", "submitted_at": datetime.now(UTC).isoformat()},
        readme_text=str(payload.get("readme") or "").strip() or None,
        requirements_text=str(payload.get("requirements_txt") or "").strip() or None,
        pyproject_text=str(payload.get("pyproject_toml") or "").strip() or None,
        dockerfile_text=str(payload.get("dockerfile") or "").strip() or None,
        env_example_text=str(payload.get("env_example") or "").strip() or None,
        screenshot_urls=screenshots,
    )


def repository_from_zip(
    data: bytes,
    filename: str,
    *,
    max_uncompressed_bytes: int,
    max_entries: int,
) -> ImportedRepository:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValidationError("Uploaded file is not a valid ZIP archive") from exc
    infos = archive.infolist()
    if not infos or len(infos) > max_entries:
        raise ValidationError("ZIP contains too many files or is empty")
    total = 0
    safe_names: list[str] = []
    for info in infos:
        path = _safe_member(info.filename)
        if info.flag_bits & 0x1:
            raise ValidationError("Encrypted ZIP files are not supported")
        # Unix symlink mode.
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise ValidationError("ZIP symbolic links are not supported")
        total += info.file_size
        if total > max_uncompressed_bytes:
            raise ValidationError("ZIP uncompressed size exceeds the configured limit")
        if not info.is_dir():
            safe_names.append(str(path))
    # Strip a common top-level folder used by GitHub ZIP exports.
    first_parts = {PurePosixPath(name).parts[0] for name in safe_names}
    prefix = (
        next(iter(first_parts)) + "/"
        if len(first_parts) == 1 and all("/" in n for n in safe_names)
        else ""
    )
    logical = {name[len(prefix) :].casefold(): name for name in safe_names if name[len(prefix) :]}
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
    screenshots: list[str] = []
    for logical_name in sorted(logical):
        if logical_name.endswith(_ALLOWED_SCREENSHOT_EXTENSIONS) and logical_name.startswith(
            ("screenshots/", "docs/", "public/", "assets/")
        ):
            # Keep an archive reference only. RegHub never executes or extracts template code.
            screenshots.append(f"local-zip://{filename}/{logical_name}")
        if len(screenshots) >= 12:
            break
    title = re.sub(r"\\.zip$", "", filename, flags=re.IGNORECASE).strip() or "Local Template"
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
            "filename": filename,
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
