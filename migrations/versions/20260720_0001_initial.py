"""Initial RegHub registry schema."""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260720_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    provider_type = sa.Enum(
        "OFFICIAL", "COMMUNITY", "PARTNER", "ORGANIZATION", "INDIVIDUAL",
        name="providertype", native_enum=False, length=32,
    )
    template_status = sa.Enum(
        "DRAFT", "PUBLISHED", "DISABLED", name="templatestatus", native_enum=False, length=32
    )
    import_status = sa.Enum(
        "PENDING", "SUCCEEDED", "FAILED", name="importstatus", native_enum=False, length=32
    )

    op.create_table(
        "categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "providers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(140), nullable=False),
        sa.Column("provider_type", provider_type, nullable=False),
        sa.Column("website_url", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "frameworks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("website_url", sa.String(500), nullable=True),
        sa.Column("icon_url", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(180), nullable=False),
        sa.Column("short_description", sa.String(320), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("repository_url", sa.String(500), nullable=False),
        sa.Column("repository_adapter", sa.String(50), nullable=False),
        sa.Column("external_repository_id", sa.String(120), nullable=True),
        sa.Column("default_branch", sa.String(255), nullable=False),
        sa.Column("homepage_url", sa.String(500), nullable=True),
        sa.Column("thumbnail_url", sa.String(500), nullable=True),
        sa.Column("license_spdx", sa.String(100), nullable=True),
        sa.Column("primary_language", sa.String(100), nullable=True),
        sa.Column("topics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("stars_count", sa.Integer(), nullable=False),
        sa.Column("forks_count", sa.Integer(), nullable=False),
        sa.Column("status", template_status, nullable=False),
        sa.Column("is_featured", sa.Boolean(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("provider_id", sa.Uuid(), nullable=True),
        sa.Column("framework_id", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_repository_id"),
        sa.UniqueConstraint("repository_url"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_templates_public_catalog", "templates", ["status", "is_featured", "created_at"])
    for column in ["status", "is_featured", "category_id", "provider_id", "framework_id", "primary_language"]:
        op.create_index(f"ix_templates_{column}", "templates", [column])

    op.create_table(
        "import_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("adapter", sa.String(50), nullable=False),
        sa.Column("repository_url", sa.String(500), nullable=False),
        sa.Column("status", import_status, nullable=False),
        sa.Column("requested_by", sa.String(255), nullable=True),
        sa.Column("metadata_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("template_id", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["template_id"], ["templates.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ["adapter", "repository_url", "status", "template_id"]:
        op.create_index(f"ix_import_history_{column}", "import_history", [column])


def downgrade() -> None:
    op.drop_table("import_history")
    op.drop_table("templates")
    op.drop_table("frameworks")
    op.drop_table("providers")
    op.drop_table("categories")
