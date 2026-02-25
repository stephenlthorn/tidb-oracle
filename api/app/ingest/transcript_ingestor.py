from __future__ import annotations

from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ingest.chorus_connector import ChorusConnector
from app.models import CallArtifact, ChorusCall, KBDocument, KBChunk, SourceType
from app.services.artifact_generator import ArtifactGenerator
from app.services.embedding import EmbeddingService
from app.utils.chunking import chunk_transcript_turns
from app.utils.hashing import sha256_text


class TranscriptIngestor:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.connector = ChorusConnector()
        self.embedder = EmbeddingService()
        self.generator = ArtifactGenerator()

    @staticmethod
    def _normalize(payload: dict) -> dict:
        # Supports already-normalized test fixtures and light transformation from API payloads.
        if "metadata" in payload and "turns" in payload:
            return payload

        participants = payload.get("participants", [])
        speaker_map = {}
        for idx, p in enumerate(participants, start=1):
            speaker_map[f"S{idx}"] = {
                "name": p.get("name", f"Speaker {idx}"),
                "role": p.get("role", "other"),
                "email": p.get("email"),
            }

        turns = payload.get("turns", [])
        if turns and "speaker_id" not in turns[0]:
            normalized_turns = []
            for t in turns:
                normalized_turns.append(
                    {
                        "speaker_id": t.get("speaker", "S1"),
                        "start_time_sec": t.get("start_time_sec", 0),
                        "end_time_sec": t.get("end_time_sec", t.get("start_time_sec", 0) + 10),
                        "text": t.get("text", ""),
                    }
                )
            turns = normalized_turns

        md = {
            "date": payload.get("date") or payload.get("metadata", {}).get("date"),
            "account": payload.get("account") or payload.get("metadata", {}).get("account") or "Unknown",
            "opportunity": payload.get("opportunity") or payload.get("metadata", {}).get("opportunity"),
            "stage": payload.get("stage") or payload.get("metadata", {}).get("stage"),
            "rep_email": payload.get("rep_email") or payload.get("metadata", {}).get("rep_email") or "unknown@pingcap.com",
            "se_email": payload.get("se_email") or payload.get("metadata", {}).get("se_email"),
        }

        return {
            "chorus_call_id": payload.get("chorus_call_id") or payload.get("id"),
            "metadata": md,
            "speaker_map": speaker_map,
            "turns": turns,
        }

    def _upsert_call(self, normalized: dict) -> ChorusCall:
        md = normalized.get("metadata", {})
        call_id = normalized["chorus_call_id"]
        existing = self.db.execute(select(ChorusCall).where(ChorusCall.chorus_call_id == call_id)).scalar_one_or_none()
        participants = list((normalized.get("speaker_map") or {}).values())

        if existing:
            row = existing
        else:
            row = ChorusCall(chorus_call_id=call_id)
            self.db.add(row)

        row.date = date.fromisoformat(md.get("date"))
        row.account = md.get("account", "Unknown")
        row.opportunity = md.get("opportunity")
        row.stage = md.get("stage")
        row.rep_email = md.get("rep_email", "unknown@pingcap.com")
        row.se_email = md.get("se_email")
        row.participants = participants
        row.recording_url = normalized.get("recording_url")
        row.transcript_url = normalized.get("transcript_url")

        self.db.flush()
        return row

    def _upsert_document(self, normalized: dict, call: ChorusCall) -> KBDocument:
        call_id = normalized["chorus_call_id"]
        doc = self.db.execute(
            select(KBDocument).where(KBDocument.source_type == SourceType.CHORUS, KBDocument.source_id == call_id)
        ).scalar_one_or_none()

        if not doc:
            doc = KBDocument(
                source_type=SourceType.CHORUS,
                source_id=call_id,
                title=f"Chorus Call: {call.account} {call.date.isoformat()}",
                url=call.transcript_url,
                mime_type="application/json",
                modified_time=None,
                owner=call.rep_email,
                path=None,
                permissions_hash=sha256_text(f"{call.rep_email}:{call.se_email or ''}"),
                tags={"account": call.account, "date": call.date.isoformat(), "source_type": "chorus"},
            )
            self.db.add(doc)
        else:
            doc.title = f"Chorus Call: {call.account} {call.date.isoformat()}"
            doc.url = call.transcript_url
            doc.owner = call.rep_email
            doc.tags = {"account": call.account, "date": call.date.isoformat(), "source_type": "chorus"}

        self.db.flush()
        return doc

    def _replace_chunks(self, doc: KBDocument, normalized: dict) -> list[str]:
        self.db.execute(delete(KBChunk).where(KBChunk.document_id == doc.id))
        chunks = chunk_transcript_turns(normalized.get("turns", []), normalized.get("speaker_map", {}))
        embeddings = self.embedder.batch_embed([c.text for c in chunks]) if chunks else []

        snippets: list[str] = []
        for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            self.db.add(
                KBChunk(
                    document_id=doc.id,
                    chunk_index=idx,
                    text=chunk.text,
                    token_count=chunk.token_count,
                    embedding=emb,
                    metadata_json=chunk.metadata,
                    content_hash=sha256_text(chunk.text),
                )
            )
            snippets.append(chunk.text[:250])
        return snippets

    def _replace_artifact(self, call_id: str, normalized: dict, snippets: list[str]) -> None:
        self.db.execute(delete(CallArtifact).where(CallArtifact.chorus_call_id == call_id))
        artifact = self.generator.generate(normalized, snippets)
        self.db.add(
            CallArtifact(
                chorus_call_id=call_id,
                summary=artifact["summary"],
                objections=artifact["objections"],
                competitors_mentioned=artifact["competitors_mentioned"],
                risks=artifact["risks"],
                next_steps=artifact["next_steps"],
                recommended_collateral=artifact["recommended_collateral"],
                follow_up_questions=artifact["follow_up_questions"],
                model_info=artifact["model_info"],
            )
        )

    def sync(self, since: date | None = None) -> dict:
        raw_calls = self.connector.fetch_calls(since=since)
        processed = 0

        for raw in raw_calls:
            normalized = self._normalize(raw.payload)
            call = self._upsert_call(normalized)
            doc = self._upsert_document(normalized, call)
            snippets = self._replace_chunks(doc, normalized)
            self._replace_artifact(normalized["chorus_call_id"], normalized, snippets)
            processed += 1

        self.db.commit()
        return {"calls_seen": len(raw_calls), "processed": processed}
