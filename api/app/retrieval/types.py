from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass
class RetrievedChunk:
    chunk_id: UUID
    document_id: UUID
    score: float
    text: str
    metadata: dict
    source_type: str
    source_id: str
    title: str
    url: str | None
    file_id: str | None
