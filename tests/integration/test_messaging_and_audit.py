from __future__ import annotations


def _sync_seed_data(client):
    client.post("/admin/sync/drive")
    client.post("/admin/sync/chorus")


def test_email_draft_blocked_for_external_recipient(client):
    _sync_seed_data(client)

    payload = {
        "chorus_call_id": "call_12345",
        "to": ["customer@gmail.com"],
        "cc": ["se@pingcap.com"],
        "mode": "send",
        "tone": "crisp",
        "include": ["recommended_next_steps", "questions", "collateral"],
    }

    res = client.post("/messages/draft", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "blocked"
    assert "restricted" in (data.get("reason_blocked") or "").lower()


def test_audit_log_contains_query_retrieval_output_mode(client):
    _sync_seed_data(client)

    payload = {
        "mode": "oracle",
        "user": "stephen.thorn@pingcap.com",
        "message": "What should we do next for Evernorth?",
        "top_k": 5,
        "filters": {"source_type": ["google_drive", "chorus"], "account": ["Evernorth"]},
    }
    chat_res = client.post("/chat", json=payload)
    assert chat_res.status_code == 200

    audit_res = client.get("/admin/audit?limit=50")
    assert audit_res.status_code == 200
    rows = audit_res.json()

    chat_rows = [r for r in rows if r.get("action") == "chat"]
    assert chat_rows, "expected at least one chat audit log"

    row = chat_rows[0]
    assert row.get("timestamp")
    assert row.get("input", {}).get("mode") == "oracle"
    assert "results" in row.get("retrieval", {})
    assert "answer" in row.get("output", {})
