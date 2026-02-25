from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.ingest.feishu_connector import FeishuConnector
from app.models import KBChunk, KBDocument, SourceType
from app.services.embedding import EmbeddingService

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 800  # tokens approx


def _chunk_text(text: str, chunk_size: int = _CHUNK_SIZE) -> list[str]:
    """Split text into chunks by approximate character count."""
    words = text.split()
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in words:
        current.append(word)
        current_len += len(word) + 1
        if current_len >= chunk_size * 4:  # ~4 chars per token
            chunks.append(" ".join(current))
            current = []
            current_len = 0
    if current:
        chunks.append(" ".join(current))
    return chunks or [""]


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class FeishuIngestor:
    """Sync documents from a Feishu folder into the knowledge base."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.connector = FeishuConnector(
            app_id=self.settings.feishu_app_id,
            app_secret=self.settings.feishu_app_secret,
            base_url=self.settings.feishu_base_url,
        )
        self.embedder = EmbeddingService()

    def sync_folder(self, folder_token: str) -> dict[str, int]:
        files = self.connector.list_folder(folder_token)
        stats: dict[str, int] = {"added": 0, "updated": 0, "skipped": 0, "errors": 0}

        for file_meta in files:
            try:
                self._sync_file(file_meta, stats)
            except Exception as exc:
                logger.error("Error syncing Feishu file %s: %s", file_meta.get("token"), exc)
                stats["errors"] += 1

        logger.info("Feishu sync complete: %s", stats)
        return stats

    def _sync_file(self, file_meta: dict, stats: dict) -> None:
        doc_token = file_meta["token"]
        source_id = f"feishu:{doc_token}"
        title = file_meta.get("name", doc_token)

        content = self.connector.get_doc_content(doc_token)
        content_hash = _content_hash(content)
        permissions_hash = _content_hash(doc_token)  # Feishu: use token as proxy

        existing = (
            self.db.query(KBDocument)
            .filter_by(source_type=SourceType.FEISHU, source_id=source_id)
            .first()
        )

        if existing:
            # Check if content has changed by comparing first chunk hash
            first_chunk = (
                self.db.query(KBChunk)
                .filter_by(document_id=existing.id, chunk_index=0)
                .first()
            )
            if first_chunk and first_chunk.content_hash == content_hash:
                stats["skipped"] += 1
                return
            # Delete old chunks
            self.db.query(KBChunk).filter_by(document_id=existing.id).delete()
            doc = existing
            stats["updated"] += 1
        else:
            doc = KBDocument(
                source_type=SourceType.FEISHU,
                source_id=source_id,
                title=title,
                url=file_meta.get("url"),
                modified_time=datetime.now(timezone.utc),
                permissions_hash=permissions_hash,
            )
            self.db.add(doc)
            self.db.flush()
            stats["added"] += 1

        # Chunk and embed
        chunks = _chunk_text(content)
        embeddings = self.embedder.batch_embed(chunks)
        for idx, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_hash = _content_hash(chunk_text)
            chunk = KBChunk(
                document_id=doc.id,
                chunk_index=idx,
                text=chunk_text,
                token_count=len(chunk_text.split()),
                embedding=embedding,
                content_hash=chunk_hash,
            )
            self.db.add(chunk)

        self.db.commit()
