from __future__ import annotations

import json
from datetime import date

from sqlalchemy import select

from app.ingest.transcript_ingestor import TranscriptIngestor
from app.models import CallArtifact, ChorusCall


def _call_payload(call_id: str, d: str):
    return {
        "chorus_call_id": call_id,
        "metadata": {
            "date": d,
            "account": "Evernorth",
            "opportunity": "Distributed SQL evaluation",
            "stage": "Technical validation",
            "rep_email": "rep@pingcap.com",
            "se_email": "se@pingcap.com",
        },
        "speaker_map": {
            "S1": {"name": "Rep", "role": "rep", "email": "rep@pingcap.com"},
            "S2": {"name": "Customer", "role": "customer", "email": None},
        },
        "turns": [
            {
                "speaker_id": "S2",
                "start_time_sec": 0,
                "end_time_sec": 55,
                "text": "We have a 40TB table and compare TiDB with SingleStore.",
            },
            {
                "speaker_id": "S1",
                "start_time_sec": 56,
                "end_time_sec": 110,
                "text": "Let's scope a POC with top queries and online DDL validation.",
            },
        ],
    }


def test_daily_sync_adds_only_new_calls_and_generates_artifacts(db_session, tmp_path):
    fake_chorus = tmp_path / "fake_chorus"
    fake_chorus.mkdir(parents=True, exist_ok=True)

    (fake_chorus / "call_1.json").write_text(json.dumps(_call_payload("call_1", "2026-02-17")), encoding="utf-8")
    (fake_chorus / "call_2.json").write_text(json.dumps(_call_payload("call_2", "2026-02-18")), encoding="utf-8")

    ingestor = TranscriptIngestor(db_session)
    ingestor.connector.fake_dir = fake_chorus

    first = ingestor.sync()
    assert first["processed"] == 2

    second = ingestor.sync(since=date.fromisoformat("2026-02-18"))
    assert second["processed"] == 0

    (fake_chorus / "call_3.json").write_text(json.dumps(_call_payload("call_3", "2026-02-19")), encoding="utf-8")
    third = ingestor.sync(since=date.fromisoformat("2026-02-18"))
    assert third["processed"] == 1

    artifacts = db_session.execute(select(CallArtifact)).scalars().all()
    assert len(artifacts) >= 3
    assert all(a.summary for a in artifacts)
    assert all(len(a.next_steps) > 0 for a in artifacts)

    calls = db_session.execute(select(ChorusCall)).scalars().all()
    assert len(calls) == 3
