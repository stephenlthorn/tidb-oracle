from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from urllib.parse import urlencode

from app.core.settings import get_settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class PendingGoogleOAuth:
    state: str
    verifier: str
    user_email: str
    redirect_uri: str
    created_at: datetime


class GoogleDriveOAuthStateStore:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._lock = Lock()
        self._pending: dict[str, PendingGoogleOAuth] = {}

    def _is_expired(self, item: PendingGoogleOAuth) -> bool:
        ttl = max(60, int(self.settings.google_drive_oauth_state_ttl_seconds))
        return _utcnow() > (item.created_at + timedelta(seconds=ttl))

    def _cleanup(self) -> None:
        expired = [state for state, item in self._pending.items() if self._is_expired(item)]
        for state in expired:
            self._pending.pop(state, None)

    @staticmethod
    def _code_challenge(verifier: str) -> str:
        import base64
        import hashlib

        digest = hashlib.sha256(verifier.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")

    def create_auth_url(self, *, user_email: str, redirect_uri: str) -> dict:
        client_id = self.settings.google_drive_client_id
        if not client_id:
            raise RuntimeError("GOOGLE_DRIVE_CLIENT_ID is not configured.")

        verifier = secrets.token_urlsafe(64)
        state = secrets.token_urlsafe(24)
        challenge = self._code_challenge(verifier)
        pending = PendingGoogleOAuth(
            state=state,
            verifier=verifier,
            user_email=user_email.strip().lower(),
            redirect_uri=redirect_uri,
            created_at=_utcnow(),
        )

        with self._lock:
            self._cleanup()
            self._pending[state] = pending

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/drive.readonly",
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
        return {"auth_url": auth_url, "state": state}

    def consume(self, *, state: str, user_email: str, redirect_uri: str) -> PendingGoogleOAuth:
        normalized = user_email.strip().lower()
        with self._lock:
            item = self._pending.pop(state, None)
            self._cleanup()
        if not item:
            raise RuntimeError("OAuth state is invalid or expired.")
        if self._is_expired(item):
            raise RuntimeError("OAuth state expired. Please reconnect Google Drive.")
        if item.user_email != normalized:
            raise RuntimeError("OAuth state does not match the signed-in user.")
        if item.redirect_uri != redirect_uri:
            raise RuntimeError("OAuth redirect URI mismatch.")
        return item


google_drive_oauth_state_store = GoogleDriveOAuthStateStore()
