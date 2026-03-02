from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from urllib.parse import urlencode

from app.core.settings import get_settings


_FEISHU_AUTH_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class PendingFeishuOAuth:
    state: str
    user_email: str
    redirect_uri: str
    app_id: str
    created_at: datetime


class FeishuOAuthStateStore:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._lock = Lock()
        self._pending: dict[str, PendingFeishuOAuth] = {}

    def _is_expired(self, item: PendingFeishuOAuth) -> bool:
        ttl = max(60, int(self.settings.feishu_oauth_state_ttl_seconds))
        return _utcnow() > (item.created_at + timedelta(seconds=ttl))

    def _cleanup(self) -> None:
        expired = [state for state, item in self._pending.items() if self._is_expired(item)]
        for state in expired:
            self._pending.pop(state, None)

    def create_auth_url(self, *, user_email: str, redirect_uri: str, app_id: str, scopes: list[str]) -> dict:
        if not app_id:
            raise RuntimeError("Feishu app_id is not configured.")

        state = secrets.token_urlsafe(24)
        pending = PendingFeishuOAuth(
            state=state,
            user_email=user_email.strip().lower(),
            redirect_uri=redirect_uri,
            app_id=app_id,
            created_at=_utcnow(),
        )

        with self._lock:
            self._cleanup()
            self._pending[state] = pending

        params = {
            "client_id": app_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
            "scope": " ".join(sorted(set(scopes))),
        }
        auth_url = f"{_FEISHU_AUTH_URL}?{urlencode(params)}"
        return {"auth_url": auth_url, "state": state}

    def consume(self, *, state: str, user_email: str, redirect_uri: str, app_id: str) -> PendingFeishuOAuth:
        normalized = user_email.strip().lower()
        with self._lock:
            item = self._pending.pop(state, None)
            self._cleanup()
        if not item:
            raise RuntimeError("OAuth state is invalid or expired.")
        if self._is_expired(item):
            raise RuntimeError("OAuth state expired. Please reconnect Feishu.")
        if item.user_email != normalized:
            raise RuntimeError("OAuth state does not match the signed-in user.")
        if item.redirect_uri != redirect_uri:
            raise RuntimeError("OAuth redirect URI mismatch.")
        if item.app_id != app_id:
            raise RuntimeError("OAuth app mismatch.")
        return item


feishu_oauth_state_store = FeishuOAuthStateStore()
