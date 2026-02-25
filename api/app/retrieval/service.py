from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import KBChunk, KBDocument
from app.retrieval.types import RetrievedChunk
from app.services.embedding import EmbeddingService


class HybridRetriever:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.embedder = EmbeddingService()

    @staticmethod
    def _cosine(a: list[float] | None, b: list[float] | None) -> float:
        if a is None or b is None:
            return 0.0
        aa_raw = list(a)
        bb_raw = list(b)
        if not aa_raw or not bb_raw:
            return 0.0
        length = min(len(aa_raw), len(bb_raw))
        if length == 0:
            return 0.0
        aa = aa_raw[:length]
        bb = bb_raw[:length]
        dot = sum(x * y for x, y in zip(aa, bb))
        na = math.sqrt(sum(x * x for x in aa)) or 1.0
        nb = math.sqrt(sum(y * y for y in bb)) or 1.0
        return dot / (na * nb)

    @staticmethod
    def _keyword_score(text: str, terms: list[str]) -> float:
        if not terms:
            return 0.0
        lowered = text.lower()
        count = Counter(term for term in terms if term and term in lowered)
        return min(1.0, sum(count.values()) / max(1, len(terms)))

    @staticmethod
    def _apply_filters(doc: KBDocument, filters: dict) -> bool:
        source_filter = {s.lower() for s in (filters.get("source_type") or [])}
        if source_filter and doc.source_type.value.lower() not in source_filter:
            return False

        account_filter = {a.lower() for a in (filters.get("account") or [])}
        if account_filter:
            tags = doc.tags if isinstance(doc.tags, dict) else {}
            account = str(tags.get("account", "")).lower()
            if account not in account_filter:
                return False
        return True

    @staticmethod
    def _source_bias(doc: KBDocument) -> float:
        title = (doc.title or "").lower()
        bias = 0.0
        if title.startswith("github/pingcap__docs/"):
            bias += 0.18
        if title.endswith((".md", ".markdown", ".rst", ".adoc")):
            bias += 0.08

        if "/test/" in title or "/tests/" in title or title.endswith("_test.go"):
            bias -= 0.20
        elif title.endswith((".go", ".java", ".kt", ".py", ".js", ".jsx", ".ts", ".tsx", ".c", ".cc", ".cpp", ".h", ".hpp", ".rs", ".proto")):
            bias -= 0.05
        return bias

    def search(self, query: str, *, top_k: int = 8, filters: dict | None = None) -> list[RetrievedChunk]:
        filters = filters or {}
        terms = [term.strip().lower() for term in query.split() if len(term.strip()) > 2]
        q_vec = self.embedder.embed(query)
        dialect = (self.db.bind.dialect.name if self.db.bind is not None else "").lower()

        source_filter = {s.lower() for s in (filters.get("source_type") or [])}
        candidate_limit = max(200, top_k * 40)

        base_stmt = select(KBChunk, KBDocument).join(KBDocument, KBChunk.document_id == KBDocument.id)
        if source_filter:
            base_stmt = base_stmt.where(KBDocument.source_type.in_(sorted(source_filter)))

        rows: list[tuple[KBChunk, KBDocument]] = []
        if dialect == "postgresql":
            try:
                vector_rows = self.db.execute(
                    base_stmt.where(KBChunk.embedding.is_not(None))
                    .order_by(KBChunk.embedding.cosine_distance(q_vec))
                    .limit(candidate_limit)
                ).all()
                rows.extend(vector_rows)
            except Exception:
                # Fallback if pgvector ordering fails in a specific environment.
                rows.extend(self.db.execute(base_stmt.limit(candidate_limit)).all())

            if terms:
                keyword_clauses = [KBChunk.text.ilike(f"%{term}%") for term in terms[:6]]
                keyword_rows = self.db.execute(
                    base_stmt.where(or_(*keyword_clauses)).limit(candidate_limit)
                ).all()
                rows.extend(keyword_rows)
        else:
            # SQLite test path: keep retrieval behavior deterministic without pgvector operators.
            rows.extend(self.db.execute(base_stmt).all())

        deduped: dict[str, tuple[KBChunk, KBDocument]] = {}
        for chunk, doc in rows:
            deduped[str(chunk.id)] = (chunk, doc)

        scored: list[tuple[float, KBChunk, KBDocument]] = []
        for chunk, doc in deduped.values():
            if not self._apply_filters(doc, filters):
                continue
            vec_score = (self._cosine(chunk.embedding, q_vec) + 1) / 2
            kw_score = self._keyword_score(chunk.text, terms)
            score = (0.7 * vec_score) + (0.3 * kw_score) + self._source_bias(doc)
            score = max(0.0, min(1.0, score))
            if score <= 0:
                continue
            scored.append((score, chunk, doc))

        scored.sort(key=lambda item: item[0], reverse=True)
        top = scored[:top_k]

        hits: list[RetrievedChunk] = []
        for score, chunk, doc in top:
            metadata = dict(chunk.metadata_json or {})
            ts = None
            if "start_time_sec" in metadata:
                ts = f"{metadata.get('start_time_sec', 0)}-{metadata.get('end_time_sec', 0)}"
            hits.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=doc.id,
                    score=round(float(score), 4),
                    text=chunk.text,
                    metadata=metadata,
                    source_type=doc.source_type.value,
                    source_id=doc.source_id,
                    title=doc.title,
                    url=doc.url,
                    file_id=doc.source_id,
                )
            )
        return hits

    @staticmethod
    def retrieval_payload(hits: list[RetrievedChunk], top_k: int) -> dict:
        return {
            "top_k": top_k,
            "results": [
                {
                    "chunk_id": str(hit.chunk_id),
                    "document_id": str(hit.document_id),
                    "score": hit.score,
                }
                for hit in hits
            ],
        }

    @staticmethod
    def serialize_hits(hits: list[RetrievedChunk]) -> list[dict]:
        return [asdict(hit) for hit in hits]
