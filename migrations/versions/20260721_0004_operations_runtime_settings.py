"""Add operations console and runtime settings.

Revision ID: 20260721_0004
Revises: 20260721_0003
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260721_0004"
down_revision: str | None = "20260721_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feature_flags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("admin_task_allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_feature_flags_key", "feature_flags", ["key"], unique=True)
    op.create_index("ix_feature_flags_category", "feature_flags", ["category"])
    op.create_index("ix_feature_flags_enabled", "feature_flags", ["enabled"])

    op.create_table(
        "integration_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("integration_type", sa.String(80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("base_url", sa.String(1000), nullable=True),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("secret_encrypted", sa.Text(), nullable=True),
        sa.Column(
            "use_environment_fallback", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(
        "ix_integration_configs_slug", "integration_configs", ["slug"], unique=True
    )
    op.create_index(
        "ix_integration_configs_integration_type",
        "integration_configs",
        ["integration_type"],
    )
    op.create_index("ix_integration_configs_enabled", "integration_configs", ["enabled"])
    op.create_index("ix_integration_configs_is_system", "integration_configs", ["is_system"])

    operation_status = sa.Enum(
        "QUEUED",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
        name="operationstatus",
        native_enum=False,
        length=32,
    )
    op.create_table(
        "admin_operations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("operation_type", sa.String(80), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("status", operation_status, nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requested_by", sa.String(255), nullable=True),
        sa.Column("return_url", sa.String(1000), nullable=True),
        sa.Column(
            "input_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("retry_of_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["retry_of_id"], ["admin_operations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_admin_operations_operation_type", "admin_operations", ["operation_type"]
    )
    op.create_index("ix_admin_operations_status", "admin_operations", ["status"])
    op.create_index("ix_admin_operations_requested_by", "admin_operations", ["requested_by"])
    op.create_index("ix_admin_operations_retry_of_id", "admin_operations", ["retry_of_id"])

    op.create_table(
        "operation_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(20), nullable=False, server_default="info"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_id"], ["admin_operations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operation_id", "sequence"),
    )
    op.create_index("ix_operation_logs_operation_id", "operation_logs", ["operation_id"])
    op.create_index("ix_operation_logs_level", "operation_logs", ["level"])


def downgrade() -> None:
    op.drop_table("operation_logs")
    op.drop_table("admin_operations")
    op.drop_table("integration_configs")
    op.drop_table("feature_flags")
