"""Add Smart Registry analysis, versions, assets, and sync history.

Revision ID: 20260720_0002
Revises: 20260720_0001
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260720_0002"
down_revision: str | None = "20260720_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.add_column("templates", sa.Column("preview_url", sa.String(500), nullable=True))
    op.add_column(
        "templates",
        sa.Column(
            "screenshots",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column("templates", sa.Column("framework_version", sa.String(80), nullable=True))
    op.add_column("templates", sa.Column("package_manager", sa.String(40), nullable=True))
    op.add_column("templates", sa.Column("difficulty", sa.String(32), nullable=True))
    op.add_column("templates", sa.Column("use_case", sa.String(160), nullable=True))
    op.add_column(
        "templates",
        sa.Column(
            "analysis",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "templates", sa.Column("quality_score", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "templates",
        sa.Column(
            "quality_breakdown",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("templates", sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("templates", sa.Column("last_analysis_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_templates_difficulty", "templates", ["difficulty"])
    op.create_index("ix_templates_use_case", "templates", ["use_case"])
    op.create_index("ix_templates_quality_score", "templates", ["quality_score"])

    op.create_table(
        "template_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("source_revision", sa.String(160), nullable=True),
        sa.Column("metadata_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("manifest_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("analysis_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["template_id"], ["templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_template_versions_template_id", "template_versions", ["template_id"])
    op.create_index("ix_template_versions_source_revision", "template_versions", ["source_revision"])

    import_status = sa.Enum(
        "PENDING", "SUCCEEDED", "FAILED", name="importstatus", native_enum=False, length=32
    )
    op.create_table(
        "sync_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("adapter", sa.String(50), nullable=False),
        sa.Column("status", import_status, nullable=False),
        sa.Column("source_revision", sa.String(160), nullable=True),
        sa.Column("metadata_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["template_id"], ["templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("template_id", "adapter", "status"):
        op.create_index(f"ix_sync_history_{column}", "sync_history", [column])

    op.create_table(
        "template_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["template_id"], ["templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_template_assets_template_id", "template_assets", ["template_id"])
    op.create_index("ix_template_assets_kind", "template_assets", ["kind"])


def downgrade() -> None:
    op.drop_table("template_assets")
    op.drop_table("sync_history")
    op.drop_table("template_versions")
    op.drop_index("ix_templates_quality_score", table_name="templates")
    op.drop_index("ix_templates_use_case", table_name="templates")
    op.drop_index("ix_templates_difficulty", table_name="templates")
    for column in (
        "last_analysis_at",
        "source_updated_at",
        "quality_breakdown",
        "quality_score",
        "analysis",
        "use_case",
        "difficulty",
        "package_manager",
        "framework_version",
        "screenshots",
        "preview_url",
    ):
        op.drop_column("templates", column)
