from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.3.2.0"
REQUIRED = (
    ".dockerignore",
    ".env.example",
    ".env.local.example",
    ".github/workflows/ci.yml",
    ".gitignore",
    "Dockerfile",
    "RELEASE_MANIFEST_V0.3.2.0.md",
    "app/__init__.py",
    "scripts/security_static_check.py",
    "scripts/verify_production_config.py",
    "scripts/verify_file_manifest.py",
    "RELEASE_FILE_MANIFEST_V0.3.2.0.json",
    "VALIDATION_REPORT_V0.3.2.0.json",
    "SECURITY.md",
    "docs/49_V0.3.2.0_PRODUCTION_READINESS.md",
    "docs/50_V0.3.2.0_UPGRADE.md",
    "docs/51_V0.3.2.0_VALIDATION.md",
)
FORBIDDEN_PARTS = {"build", "dist", "__pycache__", ".pytest_cache", ".ruff_cache"}
FORBIDDEN_NAMES = {".env", ".coverage"}


def tracked_files() -> list[Path]:
    completed = subprocess.run(  # noqa: S603, S607
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode == 0:
        return [Path(item.decode()) for item in completed.stdout.split(b"\0") if item]
    manifest = ROOT / "RELEASE_FILE_MANIFEST_V0.3.2.0.json"
    if not manifest.is_file():
        raise RuntimeError("Git metadata and release file manifest are both unavailable")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    files = [Path(item["path"]) for item in payload.get("files", [])]
    files.append(manifest.relative_to(ROOT))
    return sorted(files)


def main() -> int:
    missing = [item for item in REQUIRED if not (ROOT / item).is_file()]
    if missing:
        raise RuntimeError("Required release files are missing: " + ", ".join(missing))

    files = tracked_files()
    forbidden = [
        str(path)
        for path in files
        if FORBIDDEN_PARTS.intersection(path.parts) or path.name in FORBIDDEN_NAMES
    ]
    if forbidden:
        raise RuntimeError(
            "Forbidden generated or secret files are tracked: " + ", ".join(forbidden)
        )

    runtime_mains = [path for path in files if path.as_posix().endswith("app/main.py")]
    if runtime_mains != [Path("app/main.py")]:
        raise RuntimeError(f"Expected one runtime app/main.py, found: {runtime_mains}")

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    if project["project"]["version"] != VERSION:
        raise RuntimeError("pyproject.toml version mismatch")
    package = (ROOT / "app/__init__.py").read_text(encoding="utf-8")
    if f'__version__ = "{VERSION}"' not in package:
        raise RuntimeError("Application package version mismatch")

    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    if "COPY app ./app" in dockerfile.split("FROM python:3.13-slim AS runtime", 1)[-1]:
        raise RuntimeError("Runtime image shadows the installed wheel with a source-tree copy")
    if "USER reghub" not in dockerfile or "/api/v1/ready" not in dockerfile:
        raise RuntimeError("Docker security/readiness contract is incomplete")

    result = {
        "version": VERSION,
        "tracked_files": len(files),
        "runtime_main": runtime_mains[0].as_posix(),
        "status": "pass",
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Release-tree validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
