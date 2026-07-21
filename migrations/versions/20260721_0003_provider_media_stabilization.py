"""Add sync audit context and screenshot job tracking.

Revision ID: 20260721_0003
Revises: 20260720_0002
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260721_0003"
down_revision: str | None = "20260720_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sync_history",
        sa.Column("trigger", sa.String(40), nullable=False, server_default="legacy"),
    )
    op.add_column("sync_history", sa.Column("requested_by", sa.String(255), nullable=True))
    op.add_column(
        "sync_history",
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index("ix_sync_history_trigger", "sync_history", ["trigger"])
    op.create_index("ix_sync_history_requested_by", "sync_history", ["requested_by"])
    op.execute(
        sa.text(
            """
            INSERT INTO sync_history (
                id, template_id, adapter, status, trigger, requested_by, source_revision,
                metadata_snapshot, changes, error_message, completed_at, created_at, updated_at
            )
            SELECT
                md5(t.id::text || '-reghub-v0.2.1-sync-backfill')::uuid,
                t.id, t.repository_adapter, 'SUCCEEDED', 'backfill', t.created_by, NULL,
                '{}'::jsonb, '{"backfilled": true}'::jsonb, NULL,
                COALESCE(t.last_synced_at, t.updated_at), t.created_at, t.updated_at
            FROM templates t
            WHERE NOT EXISTS (
                SELECT 1 FROM sync_history sh WHERE sh.template_id = t.id
            )
            """
        )
    )

    screenshot_status = sa.Enum(
        "PENDING",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        name="screenshotjobstatus",
        native_enum=False,
        length=32,
    )
    op.create_table(
        "screenshot_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("status", screenshot_status, nullable=False),
        sa.Column("preview_url", sa.String(1000), nullable=False),
        sa.Column("screenshot_url", sa.String(1000), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requested_by", sa.String(255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "response_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["template_id"], ["templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_screenshot_jobs_template_id", "screenshot_jobs", ["template_id"])
    op.create_index("ix_screenshot_jobs_status", "screenshot_jobs", ["status"])
    op.create_index("ix_screenshot_jobs_requested_by", "screenshot_jobs", ["requested_by"])


def downgrade() -> None:
    op.drop_table("screenshot_jobs")
    op.drop_index("ix_sync_history_requested_by", table_name="sync_history")
    op.drop_index("ix_sync_history_trigger", table_name="sync_history")
    op.drop_column("sync_history", "changes")
    op.drop_column("sync_history", "requested_by")
    op.drop_column("sync_history", "trigger")
