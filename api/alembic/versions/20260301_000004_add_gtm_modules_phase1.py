"""add gtm module storage and kb config fields

Revision ID: 20260301_000004
Revises: 20260227_000003
Create Date: 2026-03-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260301_000004"
down_revision = "20260227_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("kb_config", sa.Column("se_poc_kit_url", sa.Text(), nullable=True))
    op.add_column(
        "kb_config",
        sa.Column(
            "feature_flags_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    op.create_table(
        "gtm_module_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("module_name", sa.String(length=128), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("retrieval", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_gtm_module_runs_module_name", "gtm_module_runs", ["module_name"])
    op.create_index("ix_gtm_module_runs_actor", "gtm_module_runs", ["actor"])
    op.create_index("ix_gtm_module_runs_module_created", "gtm_module_runs", ["module_name", "created_at"])
    op.create_index("ix_gtm_module_runs_actor_created", "gtm_module_runs", ["actor", "created_at"])

    op.create_table(
        "gtm_account_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("account", sa.String(length=255), nullable=False),
        sa.Column("territory", sa.String(length=128), nullable=True),
        sa.Column("segment", sa.String(length=128), nullable=True),
        sa.Column("industry", sa.String(length=128), nullable=True),
        sa.Column("owner_email", sa.String(length=255), nullable=True),
        sa.Column("se_email", sa.String(length=255), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_gtm_account_profiles_account", "gtm_account_profiles", ["account"])

    op.create_table(
        "gtm_risk_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("account", sa.String(length=255), nullable=False),
        sa.Column("signal_type", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("owner_email", sa.String(length=255), nullable=True),
        sa.Column("source_call_id", sa.String(length=255), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_gtm_risk_signals_account", "gtm_risk_signals", ["account"])
    op.create_index("ix_gtm_risk_signals_source_call_id", "gtm_risk_signals", ["source_call_id"])
    op.create_index("ix_gtm_risk_signals_severity", "gtm_risk_signals", ["severity"])
    op.create_index("ix_gtm_risk_signals_account_created", "gtm_risk_signals", ["account", "created_at"])

    op.create_table(
        "gtm_poc_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("account", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("readiness_score", sa.Integer(), nullable=False),
        sa.Column("readiness_summary", sa.Text(), nullable=False),
        sa.Column("plan_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("poc_kit_url", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_gtm_poc_plans_account", "gtm_poc_plans", ["account"])
    op.create_index("ix_gtm_poc_plans_status", "gtm_poc_plans", ["status"])
    op.create_index("ix_gtm_poc_plans_account_created", "gtm_poc_plans", ["account", "created_at"])

    op.create_table(
        "gtm_generated_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("account", sa.String(length=255), nullable=False),
        sa.Column("module_name", sa.String(length=128), nullable=False),
        sa.Column("asset_type", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_gtm_generated_assets_account", "gtm_generated_assets", ["account"])
    op.create_index("ix_gtm_generated_assets_module", "gtm_generated_assets", ["module_name"])
    op.create_index("ix_gtm_generated_assets_content_hash", "gtm_generated_assets", ["content_hash"])
    op.create_index("ix_gtm_generated_assets_account_created", "gtm_generated_assets", ["account", "created_at"])

    op.create_table(
        "gtm_trend_insights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("region", sa.String(length=128), nullable=False),
        sa.Column("vertical", sa.String(length=128), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("top_signals", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("recommended_plays", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_gtm_trend_insights_region", "gtm_trend_insights", ["region"])
    op.create_index("ix_gtm_trend_insights_vertical", "gtm_trend_insights", ["vertical"])
    op.create_index("ix_gtm_trend_insights_created", "gtm_trend_insights", ["created_at"])
    op.create_index("ix_gtm_trend_insights_region_vertical", "gtm_trend_insights", ["region", "vertical"])


def downgrade() -> None:
    op.drop_index("ix_gtm_trend_insights_region_vertical", table_name="gtm_trend_insights")
    op.drop_index("ix_gtm_trend_insights_created", table_name="gtm_trend_insights")
    op.drop_index("ix_gtm_trend_insights_vertical", table_name="gtm_trend_insights")
    op.drop_index("ix_gtm_trend_insights_region", table_name="gtm_trend_insights")
    op.drop_table("gtm_trend_insights")

    op.drop_index("ix_gtm_generated_assets_account_created", table_name="gtm_generated_assets")
    op.drop_index("ix_gtm_generated_assets_content_hash", table_name="gtm_generated_assets")
    op.drop_index("ix_gtm_generated_assets_module", table_name="gtm_generated_assets")
    op.drop_index("ix_gtm_generated_assets_account", table_name="gtm_generated_assets")
    op.drop_table("gtm_generated_assets")

    op.drop_index("ix_gtm_poc_plans_account_created", table_name="gtm_poc_plans")
    op.drop_index("ix_gtm_poc_plans_status", table_name="gtm_poc_plans")
    op.drop_index("ix_gtm_poc_plans_account", table_name="gtm_poc_plans")
    op.drop_table("gtm_poc_plans")

    op.drop_index("ix_gtm_risk_signals_account_created", table_name="gtm_risk_signals")
    op.drop_index("ix_gtm_risk_signals_severity", table_name="gtm_risk_signals")
    op.drop_index("ix_gtm_risk_signals_source_call_id", table_name="gtm_risk_signals")
    op.drop_index("ix_gtm_risk_signals_account", table_name="gtm_risk_signals")
    op.drop_table("gtm_risk_signals")

    op.drop_index("ix_gtm_account_profiles_account", table_name="gtm_account_profiles")
    op.drop_table("gtm_account_profiles")

    op.drop_index("ix_gtm_module_runs_actor_created", table_name="gtm_module_runs")
    op.drop_index("ix_gtm_module_runs_module_created", table_name="gtm_module_runs")
    op.drop_index("ix_gtm_module_runs_actor", table_name="gtm_module_runs")
    op.drop_index("ix_gtm_module_runs_module_name", table_name="gtm_module_runs")
    op.drop_table("gtm_module_runs")

    op.drop_column("kb_config", "feature_flags_json")
    op.drop_column("kb_config", "se_poc_kit_url")
