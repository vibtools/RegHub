from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "RELEASE_FILE_MANIFEST_V0.3.2.0.json"
EXCLUDED = {MANIFEST.relative_to(ROOT).as_posix()}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def release_files() -> list[Path]:
    completed = subprocess.run(  # noqa: S603, S607
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode == 0:
        values = [Path(item.decode()) for item in completed.stdout.split(b"\0") if item]
    else:
        forbidden_parts = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", "build", "dist"}
        values = [
            path.relative_to(ROOT)
            for path in ROOT.rglob("*")
            if path.is_file() and not forbidden_parts.intersection(path.relative_to(ROOT).parts)
        ]
    return sorted(path for path in values if path.as_posix() not in EXCLUDED)


def main() -> int:
    if not MANIFEST.is_file():
        raise RuntimeError(f"Release file manifest is missing: {MANIFEST.name}")
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if payload.get("version") != "0.3.2.0":
        raise RuntimeError("Release file manifest version mismatch")
    expected = {item["path"]: item for item in payload.get("files", [])}
    actual_paths = release_files()
    actual_names = {path.as_posix() for path in actual_paths}
    if actual_names != set(expected):
        missing = sorted(set(expected) - actual_names)
        unexpected = sorted(actual_names - set(expected))
        raise RuntimeError(
            f"Release file set mismatch; missing={missing}, unexpected={unexpected}"
        )
    mismatches: list[str] = []
    for relative in actual_paths:
        item = expected[relative.as_posix()]
        absolute = ROOT / relative
        if absolute.stat().st_size != item["size"] or sha256(absolute) != item["sha256"]:
            mismatches.append(relative.as_posix())
    if mismatches:
        raise RuntimeError("Release file hash mismatch: " + ", ".join(mismatches))
    print(json.dumps({"files": len(actual_paths), "status": "pass", "version": "0.3.2.0"}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Release file manifest validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
