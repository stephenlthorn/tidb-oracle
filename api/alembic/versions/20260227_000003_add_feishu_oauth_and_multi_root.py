"""add feishu oauth credentials and multi-root config

Revision ID: 20260227_000003
Revises: 20260227_000002
Create Date: 2026-02-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260227_000003"
down_revision = "20260227_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "kb_config",
        sa.Column("feishu_root_tokens", sa.Text(), nullable=True),
    )
    op.add_column(
        "kb_config",
        sa.Column("feishu_oauth_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.create_table(
        "feishu_user_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("token_encrypted", sa.Text(), nullable=False),
        sa.Column("scopes", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(
        "ix_feishu_user_credentials_user_email",
        "feishu_user_credentials",
        ["user_email"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_feishu_user_credentials_user_email", table_name="feishu_user_credentials")
    op.drop_table("feishu_user_credentials")
    op.drop_column("kb_config", "feishu_oauth_enabled")
    op.drop_column("kb_config", "feishu_root_tokens")
