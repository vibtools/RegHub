"""Normalize historical analysis payloads and finalize repository stabilization.

Revision ID: 20260722_0008
Revises: 20260722_0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260722_0008"
down_revision: str | None = "20260722_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TEMPLATE_ANALYSIS_SQL = sa.text(
    """
    WITH source AS (
        SELECT
            id,
            CASE
                WHEN jsonb_typeof(analysis) = 'object' THEN analysis
                ELSE '{}'::jsonb
            END AS base,
            CASE
                WHEN jsonb_typeof(quality_breakdown) = 'object' THEN quality_breakdown
                ELSE '{}'::jsonb
            END AS current_breakdown,
            LEAST(100, GREATEST(0, COALESCE(quality_score, 0))) AS current_score
        FROM templates
    ),
    normalized AS (
        SELECT
            id,
            jsonb_set(
                jsonb_set(
                    jsonb_set(
                        base
                        - 'build_command'
                        - 'start_command'
                        - 'deploy_type'
                        - 'environment',
                        '{evidence}',
                        CASE
                            WHEN jsonb_typeof(base->'evidence') = 'object'
                            THEN (base->'evidence')
                                - 'dockerfile_present'
                                - 'env_example_present'
                                - 'build_ready'
                                - 'deployment_ready'
                                - 'deployment_readiness'
                            ELSE '{}'::jsonb
                        END,
                        true
                    ),
                    '{quality_breakdown}',
                    current_breakdown
                    - 'environment'
                    - 'deployment_readiness'
                    - 'deployment-readiness',
                    true
                ),
                '{quality_score}',
                to_jsonb(current_score),
                true
            ) AS value
        FROM source
    )
    UPDATE templates AS target
    SET analysis = normalized.value
    FROM normalized
    WHERE target.id = normalized.id
      AND target.analysis IS DISTINCT FROM normalized.value
    """
)


_TEMPLATE_VERSION_ANALYSIS_SQL = sa.text(
    """
    WITH source AS (
        SELECT
            id,
            CASE
                WHEN jsonb_typeof(analysis_snapshot) = 'object' THEN analysis_snapshot
                ELSE '{}'::jsonb
            END AS base
        FROM template_versions
    ),
    prepared AS (
        SELECT
            id,
            base,
            CASE
                WHEN jsonb_typeof(base->'evidence') = 'object'
                THEN (base->'evidence')
                    - 'dockerfile_present'
                    - 'env_example_present'
                    - 'build_ready'
                    - 'deployment_ready'
                    - 'deployment_readiness'
                ELSE '{}'::jsonb
            END AS clean_evidence,
            jsonb_build_object(
                'documentation',
                    CASE
                        WHEN jsonb_typeof(base->'quality_breakdown'->'documentation') = 'number'
                        THEN (base->'quality_breakdown'->>'documentation')::integer
                        ELSE 0
                    END,
                'license',
                    CASE
                        WHEN jsonb_typeof(base->'quality_breakdown'->'license') = 'number'
                        THEN (base->'quality_breakdown'->>'license')::integer
                        ELSE 0
                    END,
                'framework',
                    CASE
                        WHEN jsonb_typeof(base->'quality_breakdown'->'framework') = 'number'
                        THEN (base->'quality_breakdown'->>'framework')::integer
                        ELSE 0
                    END,
                'metadata',
                    (CASE WHEN COALESCE(base->>'short_description', '') <> '' THEN 4 ELSE 0 END)
                    + (CASE
                        WHEN jsonb_typeof(base->'tags') = 'array'
                         AND jsonb_array_length(base->'tags') > 0
                        THEN 4 ELSE 0
                    END)
                    + (CASE WHEN COALESCE(base->>'language', '') <> '' THEN 4 ELSE 0 END),
                'visual_preview',
                    CASE
                        WHEN jsonb_typeof(base->'quality_breakdown'->'visual_preview') = 'number'
                        THEN (base->'quality_breakdown'->>'visual_preview')::integer
                        ELSE 0
                    END,
                'repository_structure',
                    CASE
                        WHEN jsonb_typeof(base->'evidence'->'root_files') = 'array'
                         AND jsonb_array_length(base->'evidence'->'root_files') > 0
                         AND (
                            base->'evidence'->>'package_json_present' = 'true'
                            OR base->'evidence'->>'requirements_present' = 'true'
                            OR base->'evidence'->>'pyproject_present' = 'true'
                         )
                        THEN 8
                        WHEN jsonb_typeof(base->'evidence'->'root_files') = 'array'
                         AND jsonb_array_length(base->'evidence'->'root_files') > 0
                        THEN 4
                        ELSE 0
                    END,
                'security',
                    CASE
                        WHEN jsonb_typeof(base->'quality_breakdown'->'security') = 'number'
                        THEN (base->'quality_breakdown'->>'security')::integer
                        ELSE 0
                    END,
                'community',
                    CASE
                        WHEN jsonb_typeof(base->'quality_breakdown'->'community') = 'number'
                        THEN (base->'quality_breakdown'->>'community')::integer
                        ELSE 0
                    END,
                'freshness',
                    CASE
                        WHEN jsonb_typeof(base->'quality_breakdown'->'freshness') = 'number'
                        THEN (base->'quality_breakdown'->>'freshness')::integer
                        ELSE 0
                    END
            ) AS breakdown
        FROM source
    ),
    normalized AS (
        SELECT
            id,
            jsonb_set(
                jsonb_set(
                    jsonb_set(
                        base
                        - 'build_command'
                        - 'start_command'
                        - 'deploy_type'
                        - 'environment',
                        '{evidence}',
                        clean_evidence,
                        true
                    ),
                    '{quality_breakdown}',
                    breakdown,
                    true
                ),
                '{quality_score}',
                to_jsonb(
                    LEAST(
                        100,
                        GREATEST(
                            0,
                            (
                                SELECT COALESCE(SUM(value::integer), 0)
                                FROM jsonb_each_text(breakdown)
                            )
                        )
                    )
                ),
                true
            ) AS value
        FROM prepared
    )
    UPDATE template_versions AS target
    SET analysis_snapshot = normalized.value
    FROM normalized
    WHERE target.id = normalized.id
      AND target.analysis_snapshot IS DISTINCT FROM normalized.value
    """
)


_IMPORT_HISTORY_ANALYSIS_SQL = sa.text(
    """
    WITH source AS (
        SELECT
            id,
            metadata_snapshot,
            metadata_snapshot->'analysis' AS base
        FROM import_history
        WHERE jsonb_typeof(metadata_snapshot) = 'object'
          AND jsonb_typeof(metadata_snapshot->'analysis') = 'object'
    ),
    prepared AS (
        SELECT
            id,
            metadata_snapshot,
            base,
            CASE
                WHEN jsonb_typeof(base->'evidence') = 'object'
                THEN (base->'evidence')
                    - 'dockerfile_present'
                    - 'env_example_present'
                    - 'build_ready'
                    - 'deployment_ready'
                    - 'deployment_readiness'
                ELSE '{}'::jsonb
            END AS clean_evidence,
            jsonb_build_object(
                'documentation',
                    CASE
                        WHEN jsonb_typeof(base->'quality_breakdown'->'documentation') = 'number'
                        THEN (base->'quality_breakdown'->>'documentation')::integer
                        ELSE 0
                    END,
                'license',
                    CASE
                        WHEN jsonb_typeof(base->'quality_breakdown'->'license') = 'number'
                        THEN (base->'quality_breakdown'->>'license')::integer
                        ELSE 0
                    END,
                'framework',
                    CASE
                        WHEN jsonb_typeof(base->'quality_breakdown'->'framework') = 'number'
                        THEN (base->'quality_breakdown'->>'framework')::integer
                        ELSE 0
                    END,
                'metadata',
                    (CASE WHEN COALESCE(base->>'short_description', '') <> '' THEN 4 ELSE 0 END)
                    + (CASE
                        WHEN jsonb_typeof(base->'tags') = 'array'
                         AND jsonb_array_length(base->'tags') > 0
                        THEN 4 ELSE 0
                    END)
                    + (CASE WHEN COALESCE(base->>'language', '') <> '' THEN 4 ELSE 0 END),
                'visual_preview',
                    CASE
                        WHEN jsonb_typeof(base->'quality_breakdown'->'visual_preview') = 'number'
                        THEN (base->'quality_breakdown'->>'visual_preview')::integer
                        ELSE 0
                    END,
                'repository_structure',
                    CASE
                        WHEN jsonb_typeof(base->'evidence'->'root_files') = 'array'
                         AND jsonb_array_length(base->'evidence'->'root_files') > 0
                         AND (
                            base->'evidence'->>'package_json_present' = 'true'
                            OR base->'evidence'->>'requirements_present' = 'true'
                            OR base->'evidence'->>'pyproject_present' = 'true'
                         )
                        THEN 8
                        WHEN jsonb_typeof(base->'evidence'->'root_files') = 'array'
                         AND jsonb_array_length(base->'evidence'->'root_files') > 0
                        THEN 4
                        ELSE 0
                    END,
                'security',
                    CASE
                        WHEN jsonb_typeof(base->'quality_breakdown'->'security') = 'number'
                        THEN (base->'quality_breakdown'->>'security')::integer
                        ELSE 0
                    END,
                'community',
                    CASE
                        WHEN jsonb_typeof(base->'quality_breakdown'->'community') = 'number'
                        THEN (base->'quality_breakdown'->>'community')::integer
                        ELSE 0
                    END,
                'freshness',
                    CASE
                        WHEN jsonb_typeof(base->'quality_breakdown'->'freshness') = 'number'
                        THEN (base->'quality_breakdown'->>'freshness')::integer
                        ELSE 0
                    END
            ) AS breakdown
        FROM source
    ),
    normalized AS (
        SELECT
            id,
            jsonb_set(
                metadata_snapshot,
                '{analysis}',
                jsonb_set(
                    jsonb_set(
                        jsonb_set(
                            base
                            - 'build_command'
                            - 'start_command'
                            - 'deploy_type'
                            - 'environment',
                            '{evidence}',
                            clean_evidence,
                            true
                        ),
                        '{quality_breakdown}',
                        breakdown,
                        true
                    ),
                    '{quality_score}',
                    to_jsonb(
                        LEAST(
                            100,
                            GREATEST(
                                0,
                                (
                                    SELECT COALESCE(SUM(value::integer), 0)
                                    FROM jsonb_each_text(breakdown)
                                )
                            )
                        )
                    ),
                    true
                ),
                true
            ) AS value
        FROM prepared
    )
    UPDATE import_history AS target
    SET metadata_snapshot = normalized.value
    FROM normalized
    WHERE target.id = normalized.id
      AND target.metadata_snapshot IS DISTINCT FROM normalized.value
    """
)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(_TEMPLATE_ANALYSIS_SQL)
    bind.execute(_TEMPLATE_VERSION_ANALYSIS_SQL)
    bind.execute(_IMPORT_HISTORY_ANALYSIS_SQL)


def downgrade() -> None:
    # Historical generated deployment metadata cannot be recreated safely.
    # The cleanup is intentionally retained on downgrade.
    pass
