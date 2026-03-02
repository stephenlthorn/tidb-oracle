from __future__ import annotations

import hashlib
import hmac
import json
import time

from app.core.settings import get_settings
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.slack import SlackService


def _signed_headers(secret: str, body: bytes) -> dict[str, str]:
    ts = str(int(time.time()))
    base = f"v0:{ts}:{body.decode('utf-8')}"
    signature = "v0=" + hmac.new(secret.encode("utf-8"), base.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "X-Slack-Request-Timestamp": ts,
        "X-Slack-Signature": signature,
    }


def test_slack_command_calls_oracle_and_returns_formatted_reply(client, monkeypatch):
    settings = get_settings()
    previous_secret = settings.slack_signing_secret
    settings.slack_signing_secret = "test-secret"

    def fake_run(self, *, mode, user, message, top_k, filters, context):
        assert mode == "oracle"
        assert "tiflash" in message.lower()
        return (
            {
                "answer": "TiFlash lag depends on write pressure and replica topology.",
                "citations": [
                    {
                        "title": "TiFlash Replica Docs",
                        "source_id": "doc_123",
                        "chunk_id": "chunk_abc",
                    }
                ],
                "follow_up_questions": ["What freshness SLO is required?"],
            },
            {"top_k": 8, "results": []},
        )

    monkeypatch.setattr(ChatOrchestrator, "run", fake_run)

    body = (
        "command=/tidb-oracle&text=What+is+TiFlash+replication+lag%3F"
        "&user_id=U123&user_name=stephen&channel_id=C123"
    ).encode("utf-8")
    headers = {
        **_signed_headers("test-secret", body),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    res = client.post("/slack/command", content=body, headers=headers)

    settings.slack_signing_secret = previous_secret

    assert res.status_code == 200
    payload = res.json()
    assert payload["response_type"] == "ephemeral"
    assert "TiFlash lag depends" in payload["text"]
    assert "Evidence" in payload["text"]


def test_slack_command_rejects_invalid_signature(client):
    settings = get_settings()
    previous_secret = settings.slack_signing_secret
    settings.slack_signing_secret = "correct-secret"

    body = b"command=/tidb-oracle&text=hello"
    headers = {
        **_signed_headers("wrong-secret", body),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    res = client.post("/slack/command", content=body, headers=headers)

    settings.slack_signing_secret = previous_secret

    assert res.status_code == 401


def test_slack_events_app_mention_posts_message(client, monkeypatch):
    settings = get_settings()
    previous_secret = settings.slack_signing_secret
    previous_bot_token = settings.slack_bot_token
    settings.slack_signing_secret = "event-secret"
    settings.slack_bot_token = "xoxb-test"

    def fake_run(self, *, mode, user, message, top_k, filters, context):
        assert mode == "oracle"
        return (
            {
                "answer": "Use a scoped POC with representative ETL and UI queries.",
                "citations": [],
                "follow_up_questions": [],
            },
            {"top_k": 8, "results": []},
        )

    posted = {}

    async def fake_post(self, *, channel, text, thread_ts=None):
        posted["channel"] = channel
        posted["text"] = text
        posted["thread_ts"] = thread_ts
        return {"ok": True}

    async def fake_resolve(self, user_id, user_name=None):
        return "stephen.thorn@pingcap.com"

    monkeypatch.setattr(ChatOrchestrator, "run", fake_run)
    monkeypatch.setattr(SlackService, "post_message", fake_post)
    monkeypatch.setattr(SlackService, "resolve_user_email", fake_resolve)

    event_body = {
        "type": "event_callback",
        "event_id": "Ev123",
        "event": {
            "type": "app_mention",
            "user": "U123",
            "text": "<@Ubot> summarize evernorth risks",
            "channel": "C123",
            "ts": "1700000000.000100",
        },
    }
    body = json.dumps(event_body).encode("utf-8")
    headers = {
        **_signed_headers("event-secret", body),
        "Content-Type": "application/json",
    }
    res = client.post("/slack/events", content=body, headers=headers)

    settings.slack_signing_secret = previous_secret
    settings.slack_bot_token = previous_bot_token

    assert res.status_code == 200
    assert res.json() == {"ok": True}
    assert posted["channel"] == "C123"
    assert "scoped POC" in posted["text"]
