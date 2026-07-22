from pathlib import Path

import pytest
from starlette.responses import RedirectResponse

from app.analyzer.models import AnalysisResult
from app.auth.routes import _clear_auth_cookies, _logout_target
from app.core.config import Settings
from app.integrations.openai.client import AIMetadataEnricher
from app.models.admin_operation import AdminOperation
from app.models.api_access import ApiAccessPolicy, ApiBlockRule
from app.models.audit_event import AuditChainState, AuditEvent
from app.models.template import Template
from app.models.template_asset import TemplateAsset
from app.registry.adapters.base import ImportedRepository
from app.registry.manifest import build_manifest


def _analysis() -> AnalysisResult:
    return AnalysisResult(
        framework_slug="astro",
        framework_name="Astro",
        framework_version="5.0.0",
        language="TypeScript",
        package_manager="pnpm",
        title="Private Template",
        short_description="Private source",
        description="Private source metadata",
        tags=["astro"],
        category_slug="general",
        difficulty="beginner",
        use_case="General web application starter",
    )


def _repository(*, private: bool) -> ImportedRepository:
    return ImportedRepository(
        adapter="github",
        external_id="private-1",
        name="private-template",
        description="Private template",
        repository_url="https://github.com/example/private-template",
        default_branch="main",
        homepage_url=None,
        license_spdx="MIT",
        topics=["astro"],
        primary_language="TypeScript",
        stars_count=0,
        forks_count=0,
        root_files=frozenset({"package.json"}),
        package_json={"dependencies": {"astro": "5.0.0"}},
        metadata={},
        is_private=private,
        readme_text="Private repository documentation",
    )


@pytest.mark.asyncio
async def test_private_repository_never_reaches_ai_transport(monkeypatch) -> None:
    class ForbiddenClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("AI transport must not be created for a private repository")

    monkeypatch.setattr("app.integrations.openai.client.httpx.AsyncClient", ForbiddenClient)
    enricher = AIMetadataEnricher(
        enabled=True,
        base_url="https://ai.example.com/v1",
        api_key="secret",
        model="metadata-model",
    )
    analysis = _analysis()
    repository = _repository(private=True)

    assert not enricher.can_enrich(repository)
    assert await enricher.enrich(repository, analysis) is analysis


def test_generated_manifest_is_deployment_neutral() -> None:
    manifest = build_manifest(
        framework_slug="astro",
        repository_url="https://github.com/example/template",
        default_branch="main",
        name="Template",
        analysis=_analysis(),
        schema_version="2.0",
    )
    value = manifest.as_dict()
    assert value["deploy"] == {"type": "unknown"}
    assert "build" not in value
    assert value["environment"] == []


def test_logout_clears_all_local_authentication_cookies() -> None:
    response = RedirectResponse("/")
    _clear_auth_cookies(response)
    cookies = response.headers.getlist("set-cookie")
    assert any(item.startswith("reghub_auth=") for item in cookies)
    assert any(item.startswith("reghub_admin_aux=") for item in cookies)
    assert any(item.startswith("reghub_oidc_state=") for item in cookies)
    assert response.headers["Cache-Control"] == "no-store"


def test_oidc_logout_target_is_fixed_to_public_base_url() -> None:
    settings = Settings(
        app_env="development",
        public_base_url="https://reghub.example.com",
        oidc_client_id="reghub",
        oidc_end_session_url="https://auth.example.com/logout",
    )
    target = _logout_target(settings)
    assert target.startswith("https://auth.example.com/logout?")
    assert "client_id=reghub" in target
    assert "post_logout_redirect_uri=https%3A%2F%2Freghub.example.com%2F" in target


def test_database_models_expose_stabilization_constraints() -> None:
    names = {
        constraint.name
        for table in (
            AdminOperation.__table__,
            ApiAccessPolicy.__table__,
            ApiBlockRule.__table__,
            AuditChainState.__table__,
            AuditEvent.__table__,
            Template.__table__,
            TemplateAsset.__table__,
        )
        for constraint in table.constraints
        if constraint.name
    }
    assert "ck_admin_operations_progress_range" in names
    assert "ck_api_access_policies_mode" in names
    assert "ck_api_block_rules_rule_type" in names
    assert "ck_audit_chain_state_singleton" in names
    assert "ck_audit_events_sequence_positive" in names
    assert "ck_templates_quality_score_range" in names
    assert "uq_template_assets_identity" in names


def test_stabilization_migration_removes_only_generated_deployment_intelligence() -> None:
    migration = Path("migrations/versions/20260722_0007_architecture_stabilization.py").read_text(
        encoding="utf-8"
    )
    for key in (
        "build_command",
        "start_command",
        "deploy_type",
        "deployment-readiness",
    ):
        assert key in migration
    assert "DROP TABLE" not in migration.upper()
