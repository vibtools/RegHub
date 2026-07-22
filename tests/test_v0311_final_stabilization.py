from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations/versions/20260722_0008_final_stabilization_hotfix.py"


def test_release_version_is_consistent() -> None:
    assert 'version = "0.3.1.1"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version="0.3.1.1"' in (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert 'version="0.3.1.1"' in (
        ROOT / "app/api/v1/catalog.py"
    ).read_text(encoding="utf-8")


def test_only_one_runtime_application_tree_exists() -> None:
    runtime_mains = [
        path.relative_to(ROOT)
        for path in ROOT.rglob("app/main.py")
        if not {".git", ".venv", "venv"}.intersection(path.parts)
    ]
    assert runtime_mains == [Path("app/main.py")]
    assert not (ROOT / "build").exists()
    assert not (ROOT / "dist").exists()


def test_generated_repository_reports_are_not_tracked() -> None:
    assert not list(ROOT.glob("BASELINE_COMPATIBILITY_V*.txt"))
    assert not list(ROOT.glob("FILE_INVENTORY_V*.txt"))
    assert not list(ROOT.glob("RELEASE_VERIFICATION_V*.txt"))


def test_dead_placeholder_integrations_are_removed() -> None:
    for relative in (
        "app/integrations/cloudflare/README.md",
        "app/integrations/coolify/README.md",
        "app/integrations/docker/README.md",
    ):
        assert not (ROOT / relative).exists()


def test_cleanup_migration_is_data_only_and_complete() -> None:
    value = MIGRATION.read_text(encoding="utf-8")
    assert 'revision: str = "20260722_0008"' in value
    assert 'down_revision: str | None = "20260722_0007"' in value
    for table in ("templates", "template_versions", "import_history"):
        assert table in value
    for obsolete in (
        "build_command",
        "start_command",
        "deploy_type",
        "environment",
        "deployment_readiness",
        "dockerfile_present",
        "env_example_present",
    ):
        assert obsolete in value
    for retained in (
        "quality_breakdown",
        "quality_score",
        "metadata",
        "repository_structure",
        "package_json_present",
        "requirements_present",
        "pyproject_present",
    ):
        assert retained in value
    upper = value.upper()
    assert "CREATE TABLE" not in upper
    assert "DROP TABLE" not in upper
    assert "ADD COLUMN" not in upper
    assert "DROP COLUMN" not in upper
    assert "ALTER COLUMN" not in upper
    assert "IS DISTINCT FROM" in upper


def test_automatic_deployment_contract_is_unchanged() -> None:
    entrypoint = (ROOT / "scripts/entrypoint.sh").read_text(encoding="utf-8")
    assert "alembic upgrade head" in entrypoint
    assert "python -m scripts.seed" in entrypoint
    assert "uvicorn app.main:app" in entrypoint
    assert (ROOT / "Dockerfile").is_file()
    assert (ROOT / ".github/workflows/ci.yml").is_file()
