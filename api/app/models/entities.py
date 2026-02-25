from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import DEFAULT_EMBEDDING_DIMENSIONS
from app.db.base import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class SourceType(str, enum.Enum):
    GOOGLE_DRIVE = "google_drive"
    FEISHU = "feishu"
    CHORUS = "chorus"
    TIDB_DOCS_ONLINE = "tidb_docs_online"


class MessageMode(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    BLOCKED = "blocked"


class MessageChannel(str, enum.Enum):
    EMAIL = "email"
    SLACK = "slack"


class AuditStatus(str, enum.Enum):
    OK = "ok"
    ERROR = "error"


def _enum_values(enum_cls):
    return [member.value for member in enum_cls]


class KBDocument(Base):
    __tablename__ = "kb_documents"
    __table_args__ = (UniqueConstraint("source_type", "source_id", name="uq_document_source"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type", values_callable=_enum_values), nullable=False, index=True
    )
    source_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(String(255))
    modified_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    owner: Mapped[str | None] = mapped_column(String(255))
    path: Mapped[str | None] = mapped_column(String(1024))
    permissions_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    tags: Mapped[dict] = mapped_column(JSONB().with_variant(JSON, "sqlite"), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    chunks: Mapped[list[KBChunk]] = relationship("KBChunk", back_populates="document", cascade="all, delete-orphan")


class KBChunk(Base):
    __tablename__ = "kb_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunk_doc_index"),
        Index("ix_kb_chunks_document_id", "document_id"),
        Index("ix_kb_chunks_content_hash", "content_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("kb_documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(DEFAULT_EMBEDDING_DIMENSIONS).with_variant(JSON, "sqlite"), nullable=True
    )
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB().with_variant(JSON, "sqlite"), default=dict, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    document: Mapped[KBDocument] = relationship("KBDocument", back_populates="chunks")


class ChorusCall(Base):
    __tablename__ = "chorus_calls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    chorus_call_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    account: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    opportunity: Mapped[str | None] = mapped_column(String(512))
    stage: Mapped[str | None] = mapped_column(String(255))
    rep_email: Mapped[str] = mapped_column(String(255), nullable=False)
    se_email: Mapped[str | None] = mapped_column(String(255))
    participants: Mapped[list[dict]] = mapped_column(JSONB().with_variant(JSON, "sqlite"), default=list, nullable=False)
    recording_url: Mapped[str | None] = mapped_column(Text)
    transcript_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CallArtifact(Base):
    __tablename__ = "call_artifacts"
    __table_args__ = (Index("ix_call_artifacts_chorus_call_id", "chorus_call_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    chorus_call_id: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    objections: Mapped[list[str]] = mapped_column(JSONB().with_variant(JSON, "sqlite"), default=list, nullable=False)
    competitors_mentioned: Mapped[list[str]] = mapped_column(JSONB().with_variant(JSON, "sqlite"), default=list, nullable=False)
    risks: Mapped[list[str]] = mapped_column(JSONB().with_variant(JSON, "sqlite"), default=list, nullable=False)
    next_steps: Mapped[list[str]] = mapped_column(JSONB().with_variant(JSON, "sqlite"), default=list, nullable=False)
    recommended_collateral: Mapped[list[dict]] = mapped_column(JSONB().with_variant(JSON, "sqlite"), default=list, nullable=False)
    follow_up_questions: Mapped[list[str]] = mapped_column(JSONB().with_variant(JSON, "sqlite"), default=list, nullable=False)
    model_info: Mapped[dict] = mapped_column(JSONB().with_variant(JSON, "sqlite"), default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OutboundMessage(Base):
    __tablename__ = "outbound_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    mode: Mapped[MessageMode] = mapped_column(
        Enum(MessageMode, name="message_mode", values_callable=_enum_values), nullable=False, index=True
    )
    channel: Mapped[MessageChannel] = mapped_column(
        Enum(MessageChannel, name="message_channel", values_callable=_enum_values), nullable=False
    )
    to_recipients: Mapped[list[str]] = mapped_column("to", JSONB().with_variant(JSON, "sqlite"), default=list, nullable=False)
    cc_recipients: Mapped[list[str]] = mapped_column("cc", JSONB().with_variant(JSON, "sqlite"), default=list, nullable=False)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    reason_blocked: Mapped[str | None] = mapped_column(Text)
    chorus_call_id: Mapped[str | None] = mapped_column(String(255), index=True)
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("call_artifacts.id", ondelete="SET NULL"), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    input_json: Mapped[dict] = mapped_column("input", JSONB().with_variant(JSON, "sqlite"), default=dict, nullable=False)
    retrieval_json: Mapped[dict] = mapped_column("retrieval", JSONB().with_variant(JSON, "sqlite"), default=dict, nullable=False)
    output_json: Mapped[dict] = mapped_column("output", JSONB().with_variant(JSON, "sqlite"), default=dict, nullable=False)
    status: Mapped[AuditStatus] = mapped_column(
        Enum(AuditStatus, name="audit_status", values_callable=_enum_values), nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text)

class KBConfig(Base):
    __tablename__ = "kb_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    google_drive_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    google_drive_folder_ids: Mapped[str | None] = mapped_column(Text)
    feishu_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    feishu_folder_token: Mapped[str | None] = mapped_column(String(255))
    feishu_app_id: Mapped[str | None] = mapped_column(String(255))
    feishu_app_secret: Mapped[str | None] = mapped_column(String(255))
    chorus_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    retrieval_top_k: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    llm_model: Mapped[str] = mapped_column(String(100), default="gpt-5.3-codex", nullable=False, server_default="gpt-5.3-codex")
    web_search_enabled: Mapped[bool] = mapped_column(default=False, nullable=False, server_default="false")
    code_interpreter_enabled: Mapped[bool] = mapped_column(default=False, nullable=False, server_default="false")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
