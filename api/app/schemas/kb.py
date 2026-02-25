from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class KBDocumentOut(BaseModel):
    id: UUID
    source_type: str
    source_id: str
    title: str
    url: str | None
    mime_type: str | None
    modified_time: datetime | None


class KBChunkOut(BaseModel):
    id: UUID
    document_id: UUID
    chunk_index: int
    text: str
    metadata: dict
    content_hash: str
