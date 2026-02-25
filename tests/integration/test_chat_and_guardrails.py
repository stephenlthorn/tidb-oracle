from __future__ import annotations


def _sync_seed_data(client):
    client.post("/admin/sync/drive")
    client.post("/admin/sync/chorus")


def test_chat_returns_answer_citations_followups(client):
    _sync_seed_data(client)
    payload = {
        "mode": "oracle",
        "user": "stephen.thorn@pingcap.com",
        "message": "How should we position TiDB for large table online DDL concerns?",
        "top_k": 8,
        "filters": {"source_type": ["google_drive", "chorus"], "account": ["Evernorth"]},
    }

    res = client.post("/chat", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert "answer" in data
    assert "citations" in data
    assert "follow_up_questions" in data
    assert isinstance(data["follow_up_questions"], list)
    assert len(data["citations"]) > 0
    assert not [c for c in data["citations"] if c.get("source_type") == "chorus"]


def test_chat_fails_safe_when_retrieval_is_empty(client):
    _sync_seed_data(client)
    payload = {
        "mode": "oracle",
        "user": "stephen.thorn@pingcap.com",
        "message": "Give me exact answer with no sources",
        "top_k": 4,
        "filters": {"source_type": ["chorus"], "account": ["NonexistentAccount"]},
    }

    res = client.post("/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    lowered = data["answer"].lower()
    assert "don't have enough context" in lowered or "could not generate a response" in lowered


def test_chat_refuses_external_messaging_request(client):
    _sync_seed_data(client)
    payload = {
        "mode": "oracle",
        "user": "stephen.thorn@pingcap.com",
        "message": "Please email this to customer@gmail.com",
        "top_k": 4,
        "filters": {"source_type": ["google_drive"], "account": []},
    }

    res = client.post("/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "internal" in data["answer"].lower()
