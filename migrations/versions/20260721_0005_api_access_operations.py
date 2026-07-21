"""Add API access control and service tokens.

Revision ID: 20260721_0005
Revises: 20260721_0004
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260721_0005"
down_revision: str | None = "20260721_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_access_policies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("mode", sa.String(24), nullable=False, server_default="development"),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_api_access_policies_key", "api_access_policies", ["key"], unique=True)
    op.create_index("ix_api_access_policies_mode", "api_access_policies", ["mode"])

    op.create_table(
        "api_service_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("token_prefix", sa.String(32), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("last_four", sa.String(8), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_api_service_tokens_name", "api_service_tokens", ["name"])
    op.create_index("ix_api_service_tokens_token_prefix", "api_service_tokens", ["token_prefix"])
    op.create_index("ix_api_service_tokens_token_hash", "api_service_tokens", ["token_hash"], unique=True)
    op.create_index("ix_api_service_tokens_enabled", "api_service_tokens", ["enabled"])
    op.create_index("ix_api_service_tokens_expires_at", "api_service_tokens", ["expires_at"])

    op.create_table(
        "api_block_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("value", sa.String(255), nullable=False),
        sa.Column("rule_type", sa.String(24), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("value"),
    )
    op.create_index("ix_api_block_rules_value", "api_block_rules", ["value"], unique=True)
    op.create_index("ix_api_block_rules_rule_type", "api_block_rules", ["rule_type"])
    op.create_index("ix_api_block_rules_enabled", "api_block_rules", ["enabled"])


def downgrade() -> None:
    op.drop_table("api_block_rules")
    op.drop_table("api_service_tokens")
    op.drop_table("api_access_policies")
