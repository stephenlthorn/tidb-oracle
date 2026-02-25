"""add feishu source type and kb_config table

Revision ID: 20260224_000002
Revises: 20260218_000001
Create Date: 2026-02-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260224_000002"
down_revision = "20260218_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add 'feishu' to source_type enum
    op.execute("ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'feishu' AFTER 'google_drive'")

    # Create kb_config table
    op.create_table(
        "kb_config",
        sa.Column("id", sa.Integer(), primary_key=True, default=1),
        sa.Column("google_drive_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("google_drive_folder_ids", sa.Text(), nullable=True),
        sa.Column("feishu_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("feishu_folder_token", sa.String(length=255), nullable=True),
        sa.Column("feishu_app_id", sa.String(length=255), nullable=True),
        sa.Column("feishu_app_secret", sa.String(length=255), nullable=True),
        sa.Column("chorus_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("retrieval_top_k", sa.Integer(), nullable=False, server_default=sa.text("8")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("kb_config")
    # Note: PostgreSQL does not support removing enum values directly.
    # To fully downgrade, the enum would need to be recreated without 'feishu'.
