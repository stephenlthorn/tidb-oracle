"""add llm config to kb_config

Revision ID: 20260225_000001
Revises: 20260224_000002
Create Date: 2026-02-25
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "20260225_000001"
down_revision = "20260224_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("kb_config", sa.Column("llm_model", sa.String(100), nullable=False, server_default="gpt-5.3-codex"))
    op.add_column("kb_config", sa.Column("web_search_enabled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("kb_config", sa.Column("code_interpreter_enabled", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("kb_config", "code_interpreter_enabled")
    op.drop_column("kb_config", "web_search_enabled")
    op.drop_column("kb_config", "llm_model")
