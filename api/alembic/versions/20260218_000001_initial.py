"""initial schema

Revision ID: 20260218_000001
Revises:
Create Date: 2026-02-18
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector


revision = "20260218_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    source_type = postgresql.ENUM("google_drive", "chorus", name="source_type", create_type=False)
    message_mode = postgresql.ENUM("draft", "sent", "blocked", name="message_mode", create_type=False)
    message_channel = postgresql.ENUM("email", "slack", name="message_channel", create_type=False)
    audit_status = postgresql.ENUM("ok", "error", name="audit_status", create_type=False)

    source_type.create(op.get_bind(), checkfirst=True)
    message_mode.create(op.get_bind(), checkfirst=True)
    message_channel.create(op.get_bind(), checkfirst=True)
    audit_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "kb_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_type", source_type, nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("modified_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner", sa.String(length=255), nullable=True),
        sa.Column("path", sa.String(length=1024), nullable=True),
        sa.Column("permissions_hash", sa.String(length=128), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("source_type", "source_id", name="uq_document_source"),
    )
    op.create_index("ix_kb_documents_source_id", "kb_documents", ["source_id"])
    op.create_index("ix_kb_documents_source_type", "kb_documents", ["source_type"])

    op.create_table(
        "kb_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kb_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_chunk_doc_index"),
    )
    op.create_index("ix_kb_chunks_document_id", "kb_chunks", ["document_id"])
    op.create_index("ix_kb_chunks_content_hash", "kb_chunks", ["content_hash"])
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_kb_chunks_embedding_ivfflat "
        "ON kb_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    op.create_table(
        "chorus_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("chorus_call_id", sa.String(length=255), nullable=False, unique=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("account", sa.String(length=255), nullable=False),
        sa.Column("opportunity", sa.String(length=512), nullable=True),
        sa.Column("stage", sa.String(length=255), nullable=True),
        sa.Column("rep_email", sa.String(length=255), nullable=False),
        sa.Column("se_email", sa.String(length=255), nullable=True),
        sa.Column("participants", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("recording_url", sa.Text(), nullable=True),
        sa.Column("transcript_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_chorus_calls_chorus_call_id", "chorus_calls", ["chorus_call_id"])
    op.create_index("ix_chorus_calls_account", "chorus_calls", ["account"])
    op.create_index("ix_chorus_calls_date", "chorus_calls", ["date"])

    op.create_table(
        "call_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("chorus_call_id", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("objections", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("competitors_mentioned", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("risks", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("next_steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("recommended_collateral", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("follow_up_questions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("model_info", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_call_artifacts_chorus_call_id", "call_artifacts", ["chorus_call_id"])

    op.create_table(
        "outbound_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("mode", message_mode, nullable=False),
        sa.Column("channel", message_channel, nullable=False),
        sa.Column("to", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("cc", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("subject", sa.String(length=512), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("reason_blocked", sa.Text(), nullable=True),
        sa.Column("chorus_call_id", sa.String(length=255), nullable=True),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("call_artifacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_outbound_messages_mode", "outbound_messages", ["mode"])
    op.create_index("ix_outbound_messages_content_hash", "outbound_messages", ["content_hash"])
    op.create_index("ix_outbound_messages_chorus_call_id", "outbound_messages", ["chorus_call_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("retrieval", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", audit_status, nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_timestamp", "audit_logs", ["timestamp"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("outbound_messages")
    op.drop_table("call_artifacts")
    op.drop_table("chorus_calls")
    op.drop_table("kb_chunks")
    op.drop_table("kb_documents")

    audit_status = sa.Enum("ok", "error", name="audit_status")
    message_channel = sa.Enum("email", "slack", name="message_channel")
    message_mode = sa.Enum("draft", "sent", "blocked", name="message_mode")
    source_type = sa.Enum("google_drive", "chorus", name="source_type")

    audit_status.drop(op.get_bind(), checkfirst=True)
    message_channel.drop(op.get_bind(), checkfirst=True)
    message_mode.drop(op.get_bind(), checkfirst=True)
    source_type.drop(op.get_bind(), checkfirst=True)
