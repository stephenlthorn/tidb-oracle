from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ingest.drive_connector import DriveConnector, DriveFile
from app.models import KBDocument, KBChunk, SourceType
from app.services.embedding import EmbeddingService
from app.services.google_drive_credentials import GoogleDriveCredentialService
from app.utils.chunking import chunk_markdown_heading_aware, chunk_pdf_pages, chunk_slides
from app.utils.hashing import sha256_text


class DriveIngestor:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.connector = DriveConnector()
        self.embedder = EmbeddingService()
        self.credential_service = GoogleDriveCredentialService(db)

    @staticmethod
    def _to_chunks(file: DriveFile):
        mime = (file.mime or "").lower()
        content = file.content or ""

        if "presentation" in mime or file.title.endswith(".slides"):
            return chunk_slides(content.split("\n---\n"))
        if "pdf" in mime:
            return chunk_pdf_pages(content.split("\f"))
        return chunk_markdown_heading_aware(content)

    @staticmethod
    def _scoped_source_id(file: DriveFile, user_email: str | None) -> str:
        if not user_email:
            return file.drive_file_id
        scope = sha256_text(user_email.strip().lower())[:12]
        return f"u_{scope}:{file.drive_file_id}"

    def _upsert_document(self, file: DriveFile, user_email: str | None = None) -> tuple[KBDocument, bool]:
        scoped_source_id = self._scoped_source_id(file, user_email)
        existing = self.db.execute(
            select(KBDocument).where(
                KBDocument.source_type == SourceType.GOOGLE_DRIVE,
                KBDocument.source_id == scoped_source_id,
            )
        ).scalar_one_or_none()

        changed = True
        normalized_user = (user_email or "").strip().lower() or None
        tags = {
            "owner": file.owner,
            "source_type": "google_drive",
            "drive_file_id": file.drive_file_id,
        }
        if normalized_user:
            tags["user_email"] = normalized_user

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
            existing.tags = tags
            doc = existing
        else:
            doc = KBDocument(
                source_type=SourceType.GOOGLE_DRIVE,
                source_id=scoped_source_id,
                title=file.title,
                url=file.url,
                mime_type=file.mime,
                modified_time=file.modified_time,
                owner=file.owner,
                path=file.path,
                permissions_hash=file.permissions_hash,
                tags=tags,
            )
            self.db.add(doc)
            changed = True

        self.db.flush()
        return doc, changed

    def sync(
        self,
        since: datetime | None = None,
        progress: Callable[[dict[str, Any]], None] | None = None,
        user_email: str | None = None,
    ) -> dict:
        normalized_user = (user_email or "").strip().lower() or None
        if normalized_user:
            try:
                creds = self.credential_service.get_google_credentials(normalized_user)
                self.connector = DriveConnector(oauth_credentials=creds)
            except RuntimeError:
                # Allow service-account mode for teams that haven't completed per-user OAuth yet.
                self.connector = DriveConnector()

        files = self.connector.list_files(since=since, progress=progress)
        indexed = 0
        skipped = 0

        if progress:
            progress(
                {
                    "phase": "indexing",
                    "files_seen": len(files),
                    "processed": 0,
                    "indexed": indexed,
                    "skipped": skipped,
                }
            )

        for idx, file in enumerate(files, start=1):
            doc, changed = self._upsert_document(file, user_email=normalized_user)
            if not changed:
                skipped += 1
                if progress:
                    progress(
                        {
                            "phase": "indexing",
                            "files_seen": len(files),
                            "processed": idx,
                            "indexed": indexed,
                            "skipped": skipped,
                            "current_file_id": file.drive_file_id,
                            "current_title": file.title,
                        }
                    )
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
            if progress:
                progress(
                    {
                        "phase": "indexing",
                        "files_seen": len(files),
                        "processed": idx,
                        "indexed": indexed,
                        "skipped": skipped,
                        "current_file_id": file.drive_file_id,
                        "current_title": file.title,
                    }
                )

        self.db.commit()
        if normalized_user:
            self.credential_service.update_last_synced(normalized_user)
        result = {"files_seen": len(files), "indexed": indexed, "skipped": skipped}
        if progress:
            progress({"phase": "completed", **result})
        return result
