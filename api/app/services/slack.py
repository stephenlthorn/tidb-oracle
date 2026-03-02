from __future__ import annotations

import hashlib
import hmac
import re
import time
from collections.abc import Mapping

import httpx

from app.core.settings import Settings, get_settings


class SlackService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def verify_signature(self, headers: Mapping[str, str], body: bytes) -> None:
        secret = (self.settings.slack_signing_secret or "").strip()
        if not secret:
            raise ValueError("Slack signing secret is not configured.")

        timestamp = (headers.get("X-Slack-Request-Timestamp") or "").strip()
        signature = (headers.get("X-Slack-Signature") or "").strip()
        if not timestamp or not signature:
            raise ValueError("Missing Slack request signature headers.")

        if not timestamp.isdigit():
            raise ValueError("Invalid Slack timestamp header.")
        request_ts = int(timestamp)
        if abs(int(time.time()) - request_ts) > 60 * 5:
            raise ValueError("Stale Slack request timestamp.")

        body_text = body.decode("utf-8", errors="replace")
        base = f"v0:{timestamp}:{body_text}"
        computed = "v0=" + hmac.new(secret.encode("utf-8"), base.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(computed, signature):
            raise ValueError("Invalid Slack request signature.")

    async def resolve_user_email(self, user_id: str | None, user_name: str | None = None) -> str:
        if user_id and self.settings.slack_bot_token:
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    resp = await client.get(
                        "https://slack.com/api/users.info",
                        params={"user": user_id},
                        headers={"Authorization": f"Bearer {self.settings.slack_bot_token}"},
                    )
                    payload = resp.json()
                    profile = (payload.get("user") or {}).get("profile") or {}
                    email = str(profile.get("email") or "").strip().lower()
                    if email:
                        return email
            except Exception:
                pass

        allowlist = self.settings.domain_allowlist
        default_domain = allowlist[0] if allowlist else "pingcap.com"
        raw = (user_name or user_id or "slack-user").strip().lower()
        local = re.sub(r"[^a-z0-9]+", ".", raw).strip(".")
        if not local:
            local = "slack-user"
        return f"{local}@{default_domain}"

    async def post_message(self, *, channel: str, text: str, thread_ts: str | None = None) -> dict:
        token = (self.settings.slack_bot_token or "").strip()
        if not token:
            raise RuntimeError("SLACK_BOT_TOKEN is not configured.")

        payload = {"channel": channel, "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts

        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(
                "https://slack.com/api/chat.postMessage",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            data = resp.json()
            if not data.get("ok", False):
                raise RuntimeError(f"Slack API error: {data.get('error', 'unknown_error')}")
            return data
