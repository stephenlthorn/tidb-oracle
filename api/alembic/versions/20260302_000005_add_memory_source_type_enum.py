"""add memory source type enum value

Revision ID: 20260302_000005
Revises: 20260301_000004
Create Date: 2026-03-02
"""

from __future__ import annotations

from alembic import op


revision = "20260302_000005"
down_revision = "20260301_000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'memory'")


def downgrade() -> None:
    # PostgreSQL does not support dropping enum values in-place.
    # Keeping downgrade as no-op to avoid destructive type recreation.
    pass
