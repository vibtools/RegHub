"""Stabilize registry security metadata and database constraints.

Revision ID: 20260722_0007
Revises: 20260721_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260722_0007"
down_revision: str | None = "20260721_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REDUNDANT_UNIQUE_INDEXES: tuple[tuple[str, str], ...] = (
    ("feature_flags", "ix_feature_flags_key"),
    ("integration_configs", "ix_integration_configs_slug"),
    ("api_access_policies", "ix_api_access_policies_key"),
    ("api_service_tokens", "ix_api_service_tokens_token_hash"),
    ("api_block_rules", "ix_api_block_rules_value"),
    ("audit_events", "ix_audit_events_sequence"),
    ("audit_events", "ix_audit_events_event_hash"),
)


def _clean_generated_manifest_intelligence(
    table_name: str, manifest_column: str, analysis_column: str
) -> None:
    # Remove only values that still match the analyzer-generated values. Administrator-curated
    # manifest overrides remain untouched for backward compatibility.
    op.execute(
        sa.text(
            f"UPDATE {table_name} SET {manifest_column} = {manifest_column} - 'build' "
            f"WHERE jsonb_typeof({manifest_column}->'build') = 'object' "
            f"AND jsonb_typeof({analysis_column}) = 'object' "
            f"AND {analysis_column} ?| ARRAY['build_command', 'start_command'] "
            f"AND (NOT ({analysis_column} ? 'build_command') OR "
            f"{manifest_column}->'build'->>'command' IS NOT DISTINCT FROM "
            f"{analysis_column}->>'build_command') "
            f"AND (NOT ({analysis_column} ? 'start_command') OR "
            f"{manifest_column}->'build'->>'start_command' IS NOT DISTINCT FROM "
            f"{analysis_column}->>'start_command')"
        )
    )
    op.execute(
        sa.text(
            f"UPDATE {table_name} SET {manifest_column} = "
            f"jsonb_set({manifest_column}, '{{deploy,type}}', '\"unknown\"'::jsonb, true) "
            f"WHERE jsonb_typeof({manifest_column}->'deploy') = 'object' "
            f"AND jsonb_typeof({analysis_column}) = 'object' "
            f"AND {analysis_column} ? 'deploy_type' "
            f"AND {manifest_column}->'deploy'->>'type' IS NOT DISTINCT FROM "
            f"{analysis_column}->>'deploy_type'"
        )
    )
    op.execute(
        sa.text(
            f"UPDATE {table_name} SET {manifest_column} = "
            f"jsonb_set({manifest_column}, '{{environment}}', '[]'::jsonb, true) "
            f"WHERE jsonb_typeof({manifest_column}->'environment') = 'array' "
            f"AND jsonb_typeof({analysis_column}->'environment') = 'array' "
            f"AND {manifest_column}->'environment' = {analysis_column}->'environment'"
        )
    )


def upgrade() -> None:
    # Align the original database column with the model's established 160-character contract.
    op.alter_column(
        "templates",
        "external_repository_id",
        existing_type=sa.String(length=120),
        type_=sa.String(length=160),
        existing_nullable=True,
    )

    # Normalize existing values before adding non-destructive integrity constraints.
    op.execute(
        sa.text(
            "UPDATE admin_operations "
            "SET progress = LEAST(100, GREATEST(0, progress)) "
            "WHERE progress < 0 OR progress > 100"
        )
    )
    op.execute(
        sa.text(
            "UPDATE templates SET "
            "quality_score = LEAST(100, GREATEST(0, quality_score)), "
            "stars_count = GREATEST(0, stars_count), "
            "forks_count = GREATEST(0, forks_count) "
            "WHERE quality_score < 0 OR quality_score > 100 "
            "OR stars_count < 0 OR forks_count < 0"
        )
    )
    op.execute(
        sa.text(
            "UPDATE screenshot_jobs SET attempts = GREATEST(0, attempts) "
            "WHERE attempts < 0"
        )
    )
    op.execute(
        sa.text(
            "UPDATE template_assets SET sort_order = GREATEST(0, sort_order) "
            "WHERE sort_order < 0"
        )
    )

    # Remove exact duplicate asset rows while preserving the oldest registry record.
    op.execute(
        sa.text(
            "WITH ranked AS ("
            "SELECT id, ROW_NUMBER() OVER ("
            "PARTITION BY template_id, kind, url, source "
            "ORDER BY created_at, id"
            ") AS duplicate_rank FROM template_assets"
            ") DELETE FROM template_assets "
            "WHERE id IN (SELECT id FROM ranked WHERE duplicate_rank > 1)"
        )
    )

    # Remove only manifest values that are provably analyzer-generated, then remove the obsolete
    # deployment-specific analysis keys. Explicit administrator-curated manifest data remains.
    _clean_generated_manifest_intelligence("templates", "manifest", "analysis")
    _clean_generated_manifest_intelligence(
        "template_versions", "manifest_snapshot", "analysis_snapshot"
    )

    op.execute(
        sa.text(
            "UPDATE templates SET analysis = analysis "
            "- 'build_command' - 'start_command' - 'deploy_type' - 'environment' "
            "WHERE analysis ?| ARRAY["
            "'build_command', 'start_command', 'deploy_type', 'environment'"
            "]"
        )
    )
    op.execute(
        sa.text(
            "UPDATE template_versions SET analysis_snapshot = analysis_snapshot "
            "- 'build_command' - 'start_command' - 'deploy_type' - 'environment' "
            "WHERE analysis_snapshot ?| ARRAY["
            "'build_command', 'start_command', 'deploy_type', 'environment'"
            "]"
        )
    )
    op.execute(
        sa.text(
            "UPDATE import_history SET metadata_snapshot = "
            "jsonb_set(metadata_snapshot, '{analysis}', "
            "(metadata_snapshot->'analysis') "
            "- 'build_command' - 'start_command' - 'deploy_type' - 'environment') "
            "WHERE metadata_snapshot IS NOT NULL "
            "AND jsonb_typeof(metadata_snapshot->'analysis') = 'object'"
        )
    )

    # Replace the obsolete deployment-readiness quality dimension with registry-only metadata
    # and repository-structure dimensions, then keep the stored total consistent with its parts.
    op.execute(
        sa.text(
            "UPDATE templates SET quality_breakdown = jsonb_build_object("
            "'documentation', CASE WHEN jsonb_typeof(quality_breakdown->'documentation') = "
            "'number' THEN (quality_breakdown->>'documentation')::integer ELSE 0 END, "
            "'license', CASE WHEN jsonb_typeof(quality_breakdown->'license') = 'number' "
            "THEN (quality_breakdown->>'license')::integer ELSE 0 END, "
            "'framework', CASE WHEN jsonb_typeof(quality_breakdown->'framework') = 'number' "
            "THEN (quality_breakdown->>'framework')::integer ELSE 0 END, "
            "'metadata', "
            "(CASE WHEN COALESCE(short_description, '') <> '' THEN 4 ELSE 0 END) + "
            "(CASE WHEN jsonb_typeof(topics) = 'array' AND jsonb_array_length(topics) > 0 "
            "THEN 4 ELSE 0 END) + "
            "(CASE WHEN COALESCE(primary_language, '') <> '' THEN 4 ELSE 0 END), "
            "'visual_preview', CASE WHEN "
            "jsonb_typeof(quality_breakdown->'visual_preview') = 'number' "
            "THEN (quality_breakdown->>'visual_preview')::integer ELSE 0 END, "
            "'repository_structure', CASE "
            "WHEN jsonb_typeof(analysis->'evidence'->'root_files') = 'array' "
            "AND jsonb_array_length(analysis->'evidence'->'root_files') > 0 "
            "AND (analysis->'evidence'->>'package_json_present' = 'true' "
            "OR analysis->'evidence'->>'requirements_present' = 'true' "
            "OR analysis->'evidence'->>'pyproject_present' = 'true') THEN 8 "
            "WHEN jsonb_typeof(analysis->'evidence'->'root_files') = 'array' "
            "AND jsonb_array_length(analysis->'evidence'->'root_files') > 0 "
            "THEN 4 ELSE 0 END, "
            "'security', CASE WHEN jsonb_typeof(quality_breakdown->'security') = 'number' "
            "THEN (quality_breakdown->>'security')::integer ELSE 0 END, "
            "'community', CASE WHEN jsonb_typeof(quality_breakdown->'community') = 'number' "
            "THEN (quality_breakdown->>'community')::integer ELSE 0 END, "
            "'freshness', CASE WHEN jsonb_typeof(quality_breakdown->'freshness') = 'number' "
            "THEN (quality_breakdown->>'freshness')::integer ELSE 0 END"
            ")"
        )
    )
    op.execute(
        sa.text(
            "UPDATE templates SET quality_score = LEAST(100, GREATEST(0, ("
            "SELECT COALESCE(SUM(value::integer), 0) "
            "FROM jsonb_each_text(quality_breakdown)"
            ")))"
        )
    )

    for table_name, index_name in _REDUNDANT_UNIQUE_INDEXES:
        op.drop_index(index_name, table_name=table_name, if_exists=True)

    op.create_check_constraint(
        "ck_admin_operations_progress_range",
        "admin_operations",
        "progress >= 0 AND progress <= 100",
    )
    op.create_check_constraint(
        "ck_templates_quality_score_range",
        "templates",
        "quality_score >= 0 AND quality_score <= 100",
    )
    op.create_check_constraint(
        "ck_templates_stars_nonnegative",
        "templates",
        "stars_count >= 0",
    )
    op.create_check_constraint(
        "ck_templates_forks_nonnegative",
        "templates",
        "forks_count >= 0",
    )
    op.create_check_constraint(
        "ck_screenshot_jobs_attempts_nonnegative",
        "screenshot_jobs",
        "attempts >= 0",
    )
    op.create_check_constraint(
        "ck_template_assets_sort_order_nonnegative",
        "template_assets",
        "sort_order >= 0",
    )
    op.create_check_constraint(
        "ck_api_access_policies_mode",
        "api_access_policies",
        "mode IN ('development', 'live')",
    )
    op.create_check_constraint(
        "ck_api_block_rules_rule_type",
        "api_block_rules",
        "rule_type IN ('ip', 'cidr', 'hostname')",
    )
    op.create_check_constraint(
        "ck_audit_chain_state_singleton",
        "audit_chain_states",
        "id = 1",
    )
    op.create_check_constraint(
        "ck_audit_chain_state_sequence_nonnegative",
        "audit_chain_states",
        "last_sequence >= 0",
    )
    op.create_check_constraint(
        "ck_audit_events_sequence_positive",
        "audit_events",
        "sequence > 0",
    )
    op.create_unique_constraint(
        "uq_template_assets_identity",
        "template_assets",
        ["template_id", "kind", "url", "source"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_template_assets_identity", "template_assets", type_="unique")
    for table_name, constraint_name in (
        ("audit_events", "ck_audit_events_sequence_positive"),
        ("audit_chain_states", "ck_audit_chain_state_sequence_nonnegative"),
        ("audit_chain_states", "ck_audit_chain_state_singleton"),
        ("api_block_rules", "ck_api_block_rules_rule_type"),
        ("api_access_policies", "ck_api_access_policies_mode"),
        ("template_assets", "ck_template_assets_sort_order_nonnegative"),
        ("screenshot_jobs", "ck_screenshot_jobs_attempts_nonnegative"),
        ("templates", "ck_templates_forks_nonnegative"),
        ("templates", "ck_templates_stars_nonnegative"),
        ("templates", "ck_templates_quality_score_range"),
        ("admin_operations", "ck_admin_operations_progress_range"),
    ):
        op.drop_constraint(constraint_name, table_name, type_="check")

    for table_name, index_name in _REDUNDANT_UNIQUE_INDEXES:
        column_name = index_name.removeprefix(f"ix_{table_name}_")
        op.create_index(index_name, table_name, [column_name], unique=True)

    # The external repository identifier remains widened to avoid destructive truncation.
    # Removed generated analysis values and duplicate asset rows are intentionally not recreated.
