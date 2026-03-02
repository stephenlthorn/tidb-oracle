from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.ingest.feishu_connector import FeishuConnector
from app.models import KBChunk, KBDocument, SourceType
from app.services.embedding import EmbeddingService
from app.utils.hashing import sha256_text

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


def _to_datetime(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, (int, float)):
        # Feishu timestamps are commonly epoch-millis.
        value = float(raw)
        if value > 1_000_000_000_000:
            value /= 1000.0
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        if text.isdigit():
            value = float(text)
            if value > 1_000_000_000_000:
                value /= 1000.0
            return datetime.fromtimestamp(value, tz=timezone.utc)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


class FeishuIngestor:
    """Sync documents from Feishu/Lark into the knowledge base."""

    def __init__(
        self,
        db: Session,
        *,
        app_id: str | None = None,
        app_secret: str | None = None,
        access_token: str | None = None,
        user_email: str | None = None,
    ) -> None:
        self.db = db
        self.settings = get_settings()
        self.user_email = (user_email or "").strip().lower() or None
        self.connector = FeishuConnector(
            app_id=(app_id or self.settings.feishu_app_id),
            app_secret=(app_secret or self.settings.feishu_app_secret),
            base_url=self.settings.feishu_base_url,
            access_token=access_token,
        )
        self.embedder = EmbeddingService()

    def _scoped_source_id(self, doc_token: str) -> str:
        base = f"feishu:{doc_token}"
        if not self.user_email:
            return base
        scope = sha256_text(self.user_email)[:12]
        return f"u_{scope}:{base}"

    def sync_folder(self, folder_token: str) -> dict[str, int]:
        return self.sync_roots([folder_token], recursive=False)

    def sync_roots(
        self,
        root_tokens: list[str],
        *,
        recursive: bool = True,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        files = self.connector.list_documents(root_tokens, recursive=recursive, progress=progress)
        stats: dict[str, Any] = {
            "files_seen": len(files),
            "added": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
            "error_samples": [],
        }

        for file_meta in files:
            try:
                self._sync_file(file_meta, stats)
            except Exception as exc:
                logger.error("Error syncing Feishu file %s: %s", file_meta.get("token"), exc)
                self.db.rollback()
                stats["errors"] += 1
                if len(stats["error_samples"]) < 3:
                    stats["error_samples"].append(
                        {
                            "token": str(file_meta.get("token") or ""),
                            "error": str(exc),
                        }
                    )

        logger.info("Feishu sync complete: %s", stats)
        return stats

    def _sync_file(self, file_meta: dict, stats: dict) -> None:
        doc_token = str(file_meta.get("token") or "").strip()
        if not doc_token:
            stats["skipped"] += 1
            return

        source_id = self._scoped_source_id(doc_token)
        title = file_meta.get("name") or file_meta.get("title") or doc_token

        content = self.connector.get_doc_content(doc_token)
        if not content.strip():
            stats["skipped"] += 1
            return

        content_hash = _content_hash(content)
        permissions_hash = _content_hash(
            f"{doc_token}|{file_meta.get('owner_id') or ''}|{file_meta.get('tenant_id') or ''}"
        )
        modified_time = (
            _to_datetime(file_meta.get("modified_time"))
            or _to_datetime(file_meta.get("edit_time"))
            or _to_datetime(file_meta.get("update_time"))
            or datetime.now(timezone.utc)
        )

        existing = (
            self.db.query(KBDocument)
            .filter_by(source_type=SourceType.FEISHU, source_id=source_id)
            .first()
        )

        tags = {
            "source_type": "feishu",
            "feishu_doc_token": doc_token,
            "root_token": file_meta.get("_root_token"),
            "content_hash": content_hash,
        }
        if self.user_email:
            tags["user_email"] = self.user_email

        if existing:
            previous_hash = str((existing.tags or {}).get("content_hash") or "")
            if previous_hash == content_hash and existing.permissions_hash == permissions_hash:
                stats["skipped"] += 1
                return

            self.db.query(KBChunk).filter_by(document_id=existing.id).delete()
            doc = existing
            doc.title = title
            doc.url = file_meta.get("url")
            doc.mime_type = "application/vnd.feishu.docx"
            doc.modified_time = modified_time
            doc.owner = file_meta.get("owner_id")
            doc.path = file_meta.get("_root_token")
            doc.permissions_hash = permissions_hash
            doc.tags = tags
            stats["updated"] += 1
        else:
            doc = KBDocument(
                source_type=SourceType.FEISHU,
                source_id=source_id,
                title=title,
                url=file_meta.get("url"),
                mime_type="application/vnd.feishu.docx",
                modified_time=modified_time,
                owner=file_meta.get("owner_id"),
                path=file_meta.get("_root_token"),
                permissions_hash=permissions_hash,
                tags=tags,
            )
            self.db.add(doc)
            self.db.flush()
            stats["added"] += 1

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
                metadata_json={
                    "source": "feishu",
                    "doc_token": doc_token,
                    "root_token": file_meta.get("_root_token"),
                },
            )
            self.db.add(chunk)

        self.db.commit()
