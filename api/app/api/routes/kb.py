from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import db_session
from app.models import AuditStatus, KBDocument, KBChunk, SourceType
from app.retrieval.service import HybridRetriever
from app.services.audit import write_audit_log

router = APIRouter()


@router.get("/documents")
def list_documents(
    source_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(db_session),
) -> list[dict]:
    stmt = select(KBDocument).order_by(KBDocument.created_at.desc()).limit(limit)
    if source_type:
        try:
            source = SourceType(source_type)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"invalid source_type: {source_type}") from exc
        stmt = stmt.where(KBDocument.source_type == source)
    docs = db.execute(stmt).scalars().all()
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
    db: Session = Depends(db_session),
) -> dict:
    retriever = HybridRetriever(db)
    filters = {}
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


@router.get("/inspect/{file_id}")
def inspect_file(file_id: str, db: Session = Depends(db_session)) -> dict:
    doc = db.execute(select(KBDocument).where(KBDocument.source_id == file_id)).scalar_one_or_none()
    if not doc:
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
