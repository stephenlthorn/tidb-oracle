from __future__ import annotations

from pathlib import Path

from app.models import KBChunk, KBDocument, SourceType
from app.ingest.drive_ingestor import DriveIngestor
from app.retrieval.service import HybridRetriever
from app.utils.hashing import sha256_text


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
    ingestor.connector._can_use_google_api = lambda: False
    result = ingestor.sync()

    assert result["files_seen"] >= 50
    assert result["indexed"] >= 50

    retriever = HybridRetriever(db_session)
    hits = retriever.search("online DDL schema guidance", top_k=8, filters={})

    assert len(hits) > 0
    assert all(hit.source_id for hit in hits)
    assert all(hit.chunk_id for hit in hits)


def test_search_viewer_filter_allows_google_shared_drive_docs_without_user_tag(db_session):
    doc_shared = KBDocument(
        source_type=SourceType.GOOGLE_DRIVE,
        source_id="drive_shared_1",
        title="Shared Drive Playbook",
        url="https://drive.google.com/file/d/drive_shared_1",
        mime_type="text/markdown",
        permissions_hash="perm_shared",
        tags={},
    )
    doc_viewer = KBDocument(
        source_type=SourceType.GOOGLE_DRIVE,
        source_id="drive_user_1",
        title="User-Scoped Drive Doc",
        url="https://drive.google.com/file/d/drive_user_1",
        mime_type="text/markdown",
        permissions_hash="perm_user",
        tags={"user_email": "rep@pingcap.com"},
    )
    doc_other = KBDocument(
        source_type=SourceType.GOOGLE_DRIVE,
        source_id="drive_other_1",
        title="Other User Drive Doc",
        url="https://drive.google.com/file/d/drive_other_1",
        mime_type="text/markdown",
        permissions_hash="perm_other",
        tags={"user_email": "other@pingcap.com"},
    )
    db_session.add_all([doc_shared, doc_viewer, doc_other])
    db_session.flush()

    chunk_shared_text = "Shared drive launch checklist and migration notes for GTM enablement."
    chunk_viewer_text = "Viewer-specific launch checklist for rep execution plan."
    chunk_other_text = "Other user content that should not be visible to this viewer."

    db_session.add_all(
        [
            KBChunk(
                document_id=doc_shared.id,
                chunk_index=0,
                text=chunk_shared_text,
                token_count=10,
                embedding=None,
                metadata_json={},
                content_hash=sha256_text(chunk_shared_text),
            ),
            KBChunk(
                document_id=doc_viewer.id,
                chunk_index=0,
                text=chunk_viewer_text,
                token_count=10,
                embedding=None,
                metadata_json={},
                content_hash=sha256_text(chunk_viewer_text),
            ),
            KBChunk(
                document_id=doc_other.id,
                chunk_index=0,
                text=chunk_other_text,
                token_count=10,
                embedding=None,
                metadata_json={},
                content_hash=sha256_text(chunk_other_text),
            ),
        ]
    )
    db_session.commit()

    retriever = HybridRetriever(db_session)
    hits = retriever.search(
        "launch checklist shared drive",
        top_k=10,
        filters={"source_type": ["google_drive"], "viewer_email": "rep@pingcap.com"},
    )
    source_ids = {hit.source_id for hit in hits}

    assert "drive_shared_1" in source_ids
    assert "drive_user_1" in source_ids
    assert "drive_other_1" not in source_ids


def test_kb_routes_allow_google_shared_drive_docs_without_user_tag(client, db_session):
    shared_doc = KBDocument(
        source_type=SourceType.GOOGLE_DRIVE,
        source_id="drive_shared_route_1",
        title="Shared Route Doc",
        url="https://drive.google.com/file/d/drive_shared_route_1",
        mime_type="text/plain",
        permissions_hash="perm_shared_route",
        tags={},
    )
    restricted_doc = KBDocument(
        source_type=SourceType.GOOGLE_DRIVE,
        source_id="drive_restricted_route_1",
        title="Restricted Route Doc",
        url="https://drive.google.com/file/d/drive_restricted_route_1",
        mime_type="text/plain",
        permissions_hash="perm_restricted_route",
        tags={"user_email": "other@pingcap.com"},
    )
    db_session.add_all([shared_doc, restricted_doc])
    db_session.flush()
    text_shared = "shared drive route visibility test"
    text_restricted = "restricted drive route visibility test"
    db_session.add_all(
        [
            KBChunk(
                document_id=shared_doc.id,
                chunk_index=0,
                text=text_shared,
                token_count=8,
                embedding=None,
                metadata_json={},
                content_hash=sha256_text(text_shared),
            ),
            KBChunk(
                document_id=restricted_doc.id,
                chunk_index=0,
                text=text_restricted,
                token_count=8,
                embedding=None,
                metadata_json={},
                content_hash=sha256_text(text_restricted),
            ),
        ]
    )
    db_session.commit()

    headers = {"X-User-Email": "rep@pingcap.com"}
    list_res = client.get("/kb/documents?source_type=google_drive", headers=headers)
    assert list_res.status_code == 200
    source_ids = {row["source_id"] for row in list_res.json()}
    assert "drive_shared_route_1" in source_ids
    assert "drive_restricted_route_1" not in source_ids

    inspect_ok = client.get("/kb/inspect/drive_shared_route_1", headers=headers)
    assert inspect_ok.status_code == 200

    inspect_blocked = client.get("/kb/inspect/drive_restricted_route_1", headers=headers)
    assert inspect_blocked.status_code == 404
