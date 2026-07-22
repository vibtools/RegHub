"""Add production governance audit chain and catalog indexes.

Revision ID: 20260721_0006
Revises: 20260721_0005
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260721_0006"
down_revision: str | None = "20260721_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "admin_operations",
        sa.Column(
            "requested_roles",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )

    op.create_table(
        "audit_chain_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("last_sequence", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_hash", sa.String(128), nullable=False, server_default="GENESIS"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        sa.text(
            "INSERT INTO audit_chain_states (id, last_sequence, last_hash, updated_at) "
            "VALUES (1, 0, 'GENESIS', CURRENT_TIMESTAMP)"
        )
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_subject", sa.String(255), nullable=True),
        sa.Column("actor_email", sa.String(320), nullable=True),
        sa.Column(
            "actor_roles",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("action", sa.String(160), nullable=False),
        sa.Column("resource_type", sa.String(120), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=False, server_default="succeeded"),
        sa.Column("request_id", sa.String(100), nullable=True),
        sa.Column("client_ip", sa.String(80), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("signing_key_id", sa.String(12), nullable=False),
        sa.Column("previous_hash", sa.String(128), nullable=False),
        sa.Column("event_hash", sa.String(128), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_hash"),
        sa.UniqueConstraint("sequence"),
    )
    for name, columns in [
        ("ix_audit_events_sequence", ["sequence"]),
        ("ix_audit_events_occurred_at", ["occurred_at"]),
        ("ix_audit_events_actor_subject", ["actor_subject"]),
        ("ix_audit_events_action", ["action"]),
        ("ix_audit_events_resource_type", ["resource_type"]),
        ("ix_audit_events_resource_id", ["resource_id"]),
        ("ix_audit_events_outcome", ["outcome"]),
        ("ix_audit_events_request_id", ["request_id"]),
        ("ix_audit_events_signing_key_id", ["signing_key_id"]),
        ("ix_audit_events_event_hash", ["event_hash"]),
    ]:
        op.create_index(name, "audit_events", columns)

    op.create_index(
        "ix_templates_catalog_updated",
        "templates",
        ["status", "updated_at", "id"],
    )
    op.create_index(
        "ix_templates_catalog_quality",
        "templates",
        ["status", "quality_score", "id"],
    )
    op.create_index(
        "ix_templates_catalog_stars",
        "templates",
        ["status", "stars_count", "id"],
    )
    op.create_index(
        "ix_templates_topics_gin",
        "templates",
        ["topics"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_templates_topics_gin", table_name="templates")
    op.drop_index("ix_templates_catalog_stars", table_name="templates")
    op.drop_index("ix_templates_catalog_quality", table_name="templates")
    op.drop_index("ix_templates_catalog_updated", table_name="templates")
    op.drop_table("audit_events")
    op.drop_table("audit_chain_states")
    op.drop_column("admin_operations", "requested_roles")
