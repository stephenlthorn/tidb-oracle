from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import db_session
from app.models import AuditStatus, KBDocument, KBChunk, SourceType
from app.retrieval.service import HybridRetriever
from app.services.audit import write_audit_log

router = APIRouter()


def _snippet(text: str, query: str, max_len: int = 220) -> str:
    source = (text or "").strip()
    if not source:
        return ""
    lowered = source.lower()
    q = query.strip().lower()
    if not q or q not in lowered:
        return source[:max_len]
    index = lowered.find(q)
    start = max(0, index - 70)
    end = min(len(source), index + len(q) + 120)
    snippet = source[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(source):
        snippet = snippet + "..."
    return snippet[:max_len + 12]


def _fulltext_score(text: str, title: str, source_id: str, query: str) -> float:
    q = query.strip().lower()
    if not q:
        return 0.0
    terms = [term for term in re.split(r"\s+", q) if term]
    if not terms:
        terms = [q]
    lowered_text = (text or "").lower()
    lowered_title = (title or "").lower()
    lowered_source_id = (source_id or "").lower()
    score = 0.0
    if q in lowered_text:
        score += 3.0
    if q in lowered_title:
        score += 6.0
    for term in terms:
        if term in lowered_title:
            score += 2.5
        if term in lowered_source_id:
            score += 1.25
        occurrences = lowered_text.count(term)
        if occurrences:
            score += min(6.0, float(occurrences))
    return score


@router.get("/documents")
def list_documents(
    source_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    request: Request = None,
    db: Session = Depends(db_session),
) -> list[dict]:
    viewer_email = (request.headers.get("X-User-Email", "") if request else "").strip().lower()
    stmt = select(KBDocument).order_by(KBDocument.created_at.desc()).limit(limit)
    if source_type:
        try:
            source = SourceType(source_type)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"invalid source_type: {source_type}") from exc
        stmt = stmt.where(KBDocument.source_type == source)
    docs = db.execute(stmt).scalars().all()
    if viewer_email:
        filtered: list[KBDocument] = []
        for doc in docs:
            if doc.source_type == SourceType.GOOGLE_DRIVE:
                tags = doc.tags if isinstance(doc.tags, dict) else {}
                indexed_for = str(tags.get("user_email", "")).strip().lower()
                if indexed_for and indexed_for != viewer_email:
                    continue
            if doc.source_type == SourceType.FEISHU:
                tags = doc.tags if isinstance(doc.tags, dict) else {}
                indexed_for = str(tags.get("user_email", "")).strip().lower()
                if indexed_for and indexed_for != viewer_email:
                    continue
            filtered.append(doc)
        docs = filtered
    return [
        {
            "id": str(doc.id),
            "source_type": doc.source_type.value,
            "source_id": doc.source_id,
            "title": doc.title,
            "url": doc.url,
            "mime_type": doc.mime_type,
            "modified_time": doc.modified_time,
        }
        for doc in docs
    ]


@router.get("/search")
def search_kb(
    q: str = Query(..., min_length=2),
    top_k: int = Query(default=8, ge=1, le=50),
    source_type: str | None = Query(default=None),
    account: str | None = Query(default=None),
    request: Request = None,
    db: Session = Depends(db_session),
) -> dict:
    retriever = HybridRetriever(db)
    filters = {}
    viewer_email = (request.headers.get("X-User-Email", "") if request else "").strip().lower()
    if viewer_email:
        filters["viewer_email"] = viewer_email
    if source_type:
        filters["source_type"] = [source_type]
    if account:
        filters["account"] = [account]

    hits = retriever.search(q, top_k=top_k, filters=filters)
    output = {
        "query": q,
        "results": [
            {
                "title": hit.title,
                "source_type": hit.source_type,
                "source_id": hit.source_id,
                "chunk_id": str(hit.chunk_id),
                "score": hit.score,
                "text": hit.text,
                "metadata": hit.metadata,
            }
            for hit in hits
        ],
    }
    write_audit_log(
        db,
        actor="system",
        action="kb_search",
        input_payload={"q": q, "top_k": top_k, "filters": filters},
        retrieval_payload=retriever.retrieval_payload(hits, top_k),
        output_payload={"count": len(output["results"])},
        status=AuditStatus.OK,
    )
    return output


@router.get("/fulltext")
def fulltext_search_kb(
    q: str = Query(..., min_length=2),
    limit: int = Query(default=40, ge=1, le=300),
    source_type: str | None = Query(default=None),
    request: Request = None,
    db: Session = Depends(db_session),
) -> dict:
    query = q.strip()
    viewer_email = (request.headers.get("X-User-Email", "") if request else "").strip().lower()

    stmt = select(KBChunk, KBDocument).join(KBDocument, KBChunk.document_id == KBDocument.id)
    if source_type:
        try:
            source = SourceType(source_type)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"invalid source_type: {source_type}") from exc
        stmt = stmt.where(KBDocument.source_type == source)

    like_query = f"%{query}%"
    stmt = stmt.where(
        or_(
            KBChunk.text.ilike(like_query),
            KBDocument.title.ilike(like_query),
            KBDocument.source_id.ilike(like_query),
        )
    )

    candidate_limit = min(2500, max(limit * 20, 500))
    rows = db.execute(stmt.limit(candidate_limit)).all()

    ranked: list[tuple[float, KBChunk, KBDocument]] = []
    for chunk, doc in rows:
        if viewer_email and doc.source_type == SourceType.GOOGLE_DRIVE:
            tags = doc.tags if isinstance(doc.tags, dict) else {}
            indexed_for = str(tags.get("user_email", "")).strip().lower()
            if indexed_for and indexed_for != viewer_email:
                continue
        if viewer_email and doc.source_type == SourceType.FEISHU:
            tags = doc.tags if isinstance(doc.tags, dict) else {}
            indexed_for = str(tags.get("user_email", "")).strip().lower()
            if indexed_for and indexed_for != viewer_email:
                continue
        score = _fulltext_score(chunk.text, doc.title or "", doc.source_id or "", query)
        if score <= 0:
            continue
        ranked.append((score, chunk, doc))

    ranked.sort(key=lambda row: row[0], reverse=True)
    top = ranked[:limit]

    output = {
        "query": query,
        "results": [
            {
                "title": doc.title,
                "source_type": doc.source_type.value,
                "source_id": doc.source_id,
                "url": doc.url,
                "chunk_id": str(chunk.id),
                "score": round(float(score), 3),
                "snippet": _snippet(chunk.text, query),
            }
            for score, chunk, doc in top
        ],
    }
    write_audit_log(
        db,
        actor=viewer_email or "system",
        action="kb_fulltext_search",
        input_payload={
            "q": query,
            "limit": limit,
            "source_type": source_type,
            "viewer_email": viewer_email or None,
        },
        retrieval_payload={"top_k": limit, "results": [{"chunk_id": item["chunk_id"]} for item in output["results"]]},
        output_payload={"count": len(output["results"])},
        status=AuditStatus.OK,
    )
    return output


@router.get("/inspect/{file_id}")
def inspect_file(file_id: str, request: Request = None, db: Session = Depends(db_session)) -> dict:
    viewer_email = (request.headers.get("X-User-Email", "") if request else "").strip().lower()
    doc = db.execute(select(KBDocument).where(KBDocument.source_id == file_id)).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="file not found")
    if viewer_email and doc.source_type == SourceType.GOOGLE_DRIVE:
        tags = doc.tags if isinstance(doc.tags, dict) else {}
        indexed_for = str(tags.get("user_email", "")).strip().lower()
        if indexed_for and indexed_for != viewer_email:
            raise HTTPException(status_code=404, detail="file not found")
    if viewer_email and doc.source_type == SourceType.FEISHU:
        tags = doc.tags if isinstance(doc.tags, dict) else {}
        indexed_for = str(tags.get("user_email", "")).strip().lower()
        if indexed_for and indexed_for != viewer_email:
            raise HTTPException(status_code=404, detail="file not found")

    chunks = db.execute(
        select(KBChunk).where(KBChunk.document_id == doc.id).order_by(KBChunk.chunk_index.asc())
    ).scalars().all()

    return {
        "document": {
            "id": str(doc.id),
            "source_type": doc.source_type.value,
            "source_id": doc.source_id,
            "title": doc.title,
            "url": doc.url,
            "mime_type": doc.mime_type,
            "modified_time": doc.modified_time,
            "owner": doc.owner,
            "path": doc.path,
            "permissions_hash": doc.permissions_hash,
            "tags": doc.tags,
        },
        "chunks": [
            {
                "id": str(chunk.id),
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "metadata": chunk.metadata_json,
                "content_hash": chunk.content_hash,
            }
            for chunk in chunks
        ],
    }
