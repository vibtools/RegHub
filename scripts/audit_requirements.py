from __future__ import annotations

import argparse
import re
from importlib.metadata import distributions
from pathlib import Path

_NORMALIZE_PATTERN = re.compile(r"[-_.]+")


def normalize_name(value: str) -> str:
    normalized = _NORMALIZE_PATTERN.sub("-", value.strip()).lower()
    if not normalized:
        raise ValueError("Distribution name cannot be empty")
    return normalized


def build_requirements(
    *,
    excluded: set[str] | None = None,
    required_present: set[str] | None = None,
) -> list[str]:
    excluded_names = {normalize_name(item) for item in (excluded or set())}
    required_names = {normalize_name(item) for item in (required_present or set())}
    seen: set[str] = set()
    versions: dict[str, str] = {}

    for distribution in distributions():
        raw_name = distribution.metadata.get("Name")
        version = str(distribution.version or "").strip()
        if not raw_name or not version:
            raise RuntimeError("Installed distribution has incomplete name/version metadata")

        name = normalize_name(raw_name)
        seen.add(name)
        if name in excluded_names:
            continue

        existing = versions.get(name)
        if existing is not None and existing != version:
            raise RuntimeError(
                f"Installed distribution {name!r} has conflicting versions: "
                f"{existing!r} and {version!r}"
            )
        versions[name] = version

    missing = sorted(required_names - seen)
    if missing:
        raise RuntimeError(
            "Required installed distributions were not present: " + ", ".join(missing)
        )
    if not versions:
        raise RuntimeError("No third-party distributions were available for auditing")

    return [f"{name}=={versions[name]}" for name in sorted(versions)]


def write_requirements(path: Path, requirements: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(requirements) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export exact installed third-party versions for strict pip-audit input."
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--require-present", action="append", default=[])
    args = parser.parse_args()

    requirements = build_requirements(
        excluded=set(args.exclude),
        required_present=set(args.require_present),
    )
    write_requirements(args.output, requirements)
    print(f"Wrote {len(requirements)} pinned third-party requirements to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
