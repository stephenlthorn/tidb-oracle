from __future__ import annotations

from pathlib import Path

from app.ingest.drive_ingestor import DriveIngestor
from app.retrieval.service import HybridRetriever


def test_ingest_50_plus_docs_and_search_citations(db_session, tmp_path):
    fake_drive = tmp_path / "fake_drive"
    fake_drive.mkdir(parents=True, exist_ok=True)

    for i in range(1, 56):
        (fake_drive / f"doc_{i:02d}.md").write_text(
            f"# Doc {i}\n\nTiDB online DDL guidance for account {i}.\n\n## Notes\nSchema changes and scaling practices.",
            encoding="utf-8",
        )

    ingestor = DriveIngestor(db_session)
    ingestor.connector.fake_dir = fake_drive
    result = ingestor.sync()

    assert result["files_seen"] >= 50
    assert result["indexed"] >= 50

    retriever = HybridRetriever(db_session)
    hits = retriever.search("online DDL schema guidance", top_k=8, filters={})

    assert len(hits) > 0
    assert all(hit.source_id for hit in hits)
    assert all(hit.chunk_id for hit in hits)
