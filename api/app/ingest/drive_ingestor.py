from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ingest.drive_connector import DriveConnector, DriveFile
from app.models import KBDocument, KBChunk, SourceType
from app.services.embedding import EmbeddingService
from app.utils.chunking import chunk_markdown_heading_aware, chunk_pdf_pages, chunk_slides
from app.utils.hashing import sha256_text


class DriveIngestor:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.connector = DriveConnector()
        self.embedder = EmbeddingService()

    @staticmethod
    def _to_chunks(file: DriveFile):
        mime = (file.mime or "").lower()
        content = file.content or ""

        if "presentation" in mime or file.title.endswith(".slides"):
            return chunk_slides(content.split("\n---\n"))
        if "pdf" in mime:
            return chunk_pdf_pages(content.split("\f"))
        return chunk_markdown_heading_aware(content)

    def _upsert_document(self, file: DriveFile) -> tuple[KBDocument, bool]:
        existing = self.db.execute(
            select(KBDocument).where(
                KBDocument.source_type == SourceType.GOOGLE_DRIVE,
                KBDocument.source_id == file.drive_file_id,
            )
        ).scalar_one_or_none()

        changed = True
        if existing:
            if existing.modified_time and existing.modified_time >= file.modified_time and existing.permissions_hash == file.permissions_hash:
                changed = False
            existing.title = file.title
            existing.url = file.url
            existing.mime_type = file.mime
            existing.modified_time = file.modified_time
            existing.owner = file.owner
            existing.path = file.path
            existing.permissions_hash = file.permissions_hash
            existing.tags = {"owner": file.owner, "source_type": "google_drive"}
            doc = existing
        else:
            doc = KBDocument(
                source_type=SourceType.GOOGLE_DRIVE,
                source_id=file.drive_file_id,
                title=file.title,
                url=file.url,
                mime_type=file.mime,
                modified_time=file.modified_time,
                owner=file.owner,
                path=file.path,
                permissions_hash=file.permissions_hash,
                tags={"owner": file.owner, "source_type": "google_drive"},
            )
            self.db.add(doc)
            changed = True

        self.db.flush()
        return doc, changed

    def sync(self, since: datetime | None = None) -> dict:
        files = self.connector.list_files(since=since)
        indexed = 0
        skipped = 0

        for file in files:
            doc, changed = self._upsert_document(file)
            if not changed:
                skipped += 1
                continue

            self.db.execute(delete(KBChunk).where(KBChunk.document_id == doc.id))

            chunks = self._to_chunks(file)
            embeddings = self.embedder.batch_embed([chunk.text for chunk in chunks]) if chunks else []

            for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                row = KBChunk(
                    document_id=doc.id,
                    chunk_index=idx,
                    text=chunk.text,
                    token_count=chunk.token_count,
                    embedding=emb,
                    metadata_json=chunk.metadata,
                    content_hash=sha256_text(chunk.text),
                )
                self.db.add(row)

            indexed += 1

        self.db.commit()
        return {"files_seen": len(files), "indexed": indexed, "skipped": skipped}
