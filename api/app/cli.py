from __future__ import annotations

import json
from datetime import datetime

import typer
from dateutil.parser import isoparse
from sqlalchemy import select

from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.ingest.drive_ingestor import DriveIngestor
from app.models import KBDocument, KBChunk
from app.retrieval.service import HybridRetriever

app = typer.Typer(help="TiDB Oracle knowledge base CLI")


@app.command("sync")
def kb_sync(since: str | None = typer.Option(default=None, help="ISO timestamp")) -> None:
    since_dt = isoparse(since) if since else None
    init_db()
    with SessionLocal() as db:
        result = DriveIngestor(db).sync(since=since_dt)
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command("search")
def kb_search(query: str, topk: int = 8) -> None:
    init_db()
    with SessionLocal() as db:
        hits = HybridRetriever(db).search(query, top_k=topk, filters={})
    typer.echo(
        json.dumps(
            [
                {
                    "title": h.title,
                    "source_id": h.source_id,
                    "chunk_id": str(h.chunk_id),
                    "score": h.score,
                    "snippet": h.text[:180],
                }
                for h in hits
            ],
            indent=2,
            default=str,
        )
    )


@app.command("inspect")
def kb_inspect(file_id: str) -> None:
    init_db()
    with SessionLocal() as db:
        doc = db.execute(select(KBDocument).where(KBDocument.source_id == file_id)).scalar_one_or_none()
        if not doc:
            typer.echo(f"No document found for source_id={file_id}")
            raise typer.Exit(code=1)

        chunks = db.execute(select(KBChunk).where(KBChunk.document_id == doc.id).order_by(KBChunk.chunk_index.asc())).scalars().all()

    payload = {
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
        },
        "chunks": [
            {
                "id": str(c.id),
                "chunk_index": c.chunk_index,
                "metadata": c.metadata_json,
                "content_hash": c.content_hash,
                "text": c.text,
            }
            for c in chunks
        ],
    }
    typer.echo(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    app()
