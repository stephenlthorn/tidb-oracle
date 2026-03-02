"""add persona prompt fields to kb_config

Revision ID: 20260227_000001
Revises: 20260225_000001
Create Date: 2026-02-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260227_000001"
down_revision = "20260225_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "kb_config",
        sa.Column("persona_name", sa.String(length=64), nullable=False, server_default="sales_representative"),
    )
    op.add_column("kb_config", sa.Column("persona_prompt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("kb_config", "persona_prompt")
    op.drop_column("kb_config", "persona_name")
