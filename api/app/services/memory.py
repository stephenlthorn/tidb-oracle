from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import KBChunk, KBDocument, SourceType
from app.services.embedding import EmbeddingService
from app.utils.chunking import estimate_tokens
from app.utils.hashing import sha256_text


class MemoryService:
    """Persist user interactions as retrievable long-term memory chunks."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.embedder = EmbeddingService()

    @staticmethod
    def _build_memory_text(*, mode: str, message: str, response_payload: dict, retrieval_payload: dict) -> str:
        answer = (
            response_payload.get("answer")
            or response_payload.get("summary")
            or response_payload.get("readiness_summary")
            or ""
        )

        bullets: list[str] = []
        for key in (
            "follow_up_questions",
            "next_steps",
            "questions",
            "top_signals",
            "campaign_angles",
            "action_plan",
        ):
            value = response_payload.get(key)
            if isinstance(value, list):
                bullets.extend([str(item).strip() for item in value[:6] if str(item).strip()])

        top_results = retrieval_payload.get("results") if isinstance(retrieval_payload, dict) else []
        if isinstance(top_results, list):
            refs = [str(row.get("chunk_id")) for row in top_results[:5] if isinstance(row, dict)]
        else:
            refs = []

        lines = [
            f"Mode: {mode}",
            f"User ask: {message.strip()}",
            f"Response: {str(answer).strip()}",
        ]

        if bullets:
            lines.append("Key outputs:")
            lines.extend([f"- {item}" for item in bullets[:8]])

        if refs:
            lines.append("Retrieved chunk ids:")
            lines.extend([f"- {item}" for item in refs])

        return "\n".join(lines).strip()

    def _upsert_daily_document(self, *, actor: str) -> KBDocument:
        today = datetime.now(timezone.utc).date().isoformat()
        source_id = f"{actor}:{today}"
        row = self.db.execute(
            select(KBDocument).where(
                KBDocument.source_type == SourceType.MEMORY,
                KBDocument.source_id == source_id,
            )
        ).scalar_one_or_none()

        if row is None:
            row = KBDocument(
                source_type=SourceType.MEMORY,
                source_id=source_id,
                title=f"Memory: {actor} ({today})",
                url=None,
                mime_type="text/plain",
                modified_time=datetime.now(timezone.utc),
                owner=actor,
                path=f"memory/{actor}/{today}",
                permissions_hash=sha256_text(actor),
                tags={
                    "source_type": "memory",
                    "user_email": actor,
                    "day": today,
                },
            )
            self.db.add(row)
            self.db.flush()
        else:
            row.modified_time = datetime.now(timezone.utc)
            self.db.add(row)
            self.db.flush()

        return row

    def _next_chunk_index(self, document_id) -> int:
        value = self.db.execute(
            select(func.max(KBChunk.chunk_index)).where(KBChunk.document_id == document_id)
        ).scalar_one_or_none()
        if value is None:
            return 0
        return int(value) + 1

    def capture_interaction(
        self,
        *,
        actor: str,
        mode: str,
        message: str,
        response_payload: dict,
        retrieval_payload: dict,
    ) -> None:
        actor_email = (actor or "").strip().lower()
        if not actor_email or not message.strip():
            return

        text = self._build_memory_text(
            mode=mode,
            message=message,
            response_payload=response_payload,
            retrieval_payload=retrieval_payload,
        )
        if len(text) < 25:
            return

        doc = self._upsert_daily_document(actor=actor_email)
        chunk_index = self._next_chunk_index(doc.id)

        self.db.add(
            KBChunk(
                document_id=doc.id,
                chunk_index=chunk_index,
                text=text,
                token_count=estimate_tokens(text),
                embedding=self.embedder.embed(text),
                metadata_json={
                    "memory": True,
                    "mode": mode,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                },
                content_hash=sha256_text(text),
            )
        )
        self.db.commit()
