import io
import json
import zipfile

import pytest

from app.core.exceptions import ValidationError
from app.registry.local import repository_from_manifest, repository_from_zip


def make_zip(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return output.getvalue()


def test_manifest_import() -> None:
    repository = repository_from_manifest(
        {
            "name": "Local Astro",
            "framework": "astro",
            "repository": "https://github.com/ygit/local-astro",
            "branch": "main",
            "topics": ["landing"],
        }
    )
    assert repository.adapter == "local-manifest"
    assert "astro" in repository.topics


def test_zip_import_reads_safe_metadata() -> None:
    data = make_zip(
        {
            "starter/package.json": json.dumps(
                {"dependencies": {"next": "15.0.0"}, "scripts": {"build": "next build"}}
            ).encode(),
            "starter/README.md": b"# Starter\n" + b"Docs " * 100,
            "starter/.env.example": b"DATABASE_URL=change-me\n",
            "starter/public/screenshot.png": b"not-an-image-but-never-executed",
        }
    )
    repository = repository_from_zip(
        data,
        "starter.zip",
        max_uncompressed_bytes=5_000_000,
        max_entries=100,
    )
    assert repository.adapter == "local-zip"
    assert repository.package_json["dependencies"]["next"] == "15.0.0"
    assert repository.readme_text.startswith("# Starter")
    assert repository.env_example_text
    assert repository.screenshot_urls


def test_zip_rejects_path_traversal() -> None:
    data = make_zip({"../evil.txt": b"no"})
    with pytest.raises(ValidationError, match="unsafe"):
        repository_from_zip(
            data,
            "bad.zip",
            max_uncompressed_bytes=1000,
            max_entries=10,
        )


def test_zip_rejects_uncompressed_limit() -> None:
    data = make_zip({"large.txt": b"x" * 5000})
    with pytest.raises(ValidationError, match="uncompressed"):
        repository_from_zip(
            data,
            "large.zip",
            max_uncompressed_bytes=100,
            max_entries=10,
        )
