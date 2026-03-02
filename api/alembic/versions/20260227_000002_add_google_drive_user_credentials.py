"""add google drive user credentials table

Revision ID: 20260227_000002
Revises: 20260227_000001
Create Date: 2026-02-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260227_000002"
down_revision = "20260227_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_drive_user_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("token_encrypted", sa.Text(), nullable=False),
        sa.Column("scopes", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(
        "ix_google_drive_user_credentials_user_email",
        "google_drive_user_credentials",
        ["user_email"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_google_drive_user_credentials_user_email", table_name="google_drive_user_credentials")
    op.drop_table("google_drive_user_credentials")
