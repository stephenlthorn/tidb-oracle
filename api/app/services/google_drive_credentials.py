from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models import GoogleDriveUserCredential
from app.services.token_crypto import TokenCrypto


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_expiry_for_google(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    # google-auth compares against naive UTC internally.
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


class GoogleDriveCredentialService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.crypto = TokenCrypto()

    @staticmethod
    def _normalize_email(email: str) -> str:
        return (email or "").strip().lower()

    def _row_for(self, user_email: str) -> GoogleDriveUserCredential | None:
        normalized = self._normalize_email(user_email)
        if not normalized:
            return None
        return self.db.execute(
            select(GoogleDriveUserCredential).where(GoogleDriveUserCredential.user_email == normalized)
        ).scalar_one_or_none()

    def row_for_user(self, user_email: str) -> GoogleDriveUserCredential | None:
        return self._row_for(user_email)

    def upsert_token_payload(self, user_email: str, payload: dict, *, commit: bool = True) -> GoogleDriveUserCredential:
        normalized = self._normalize_email(user_email)
        if not normalized:
            raise RuntimeError("A valid user email is required for Google Drive credentials.")

        row = self._row_for(normalized)
        if row is None:
            row = GoogleDriveUserCredential(user_email=normalized, token_encrypted="", scopes=None)

        encrypted = self.crypto.encrypt(json.dumps(payload))
        scopes = payload.get("scope") or payload.get("scopes")
        if isinstance(scopes, list):
            scopes = " ".join(str(item) for item in scopes if str(item).strip())
        row.token_encrypted = encrypted
        row.scopes = str(scopes).strip() if isinstance(scopes, str) and scopes.strip() else row.scopes
        row.updated_at = _utcnow()

        self.db.add(row)
        if commit:
            self.db.commit()
            self.db.refresh(row)
        return row

    def delete_for_user(self, user_email: str, *, commit: bool = True) -> bool:
        row = self._row_for(user_email)
        if not row:
            return False
        self.db.delete(row)
        if commit:
            self.db.commit()
        return True

    def get_status(self, user_email: str) -> dict:
        row = self._row_for(user_email)
        if not row:
            return {
                "connected": False,
                "user_email": self._normalize_email(user_email),
                "scopes": [],
                "last_synced_at": None,
                "updated_at": None,
            }
        scopes = []
        if row.scopes:
            scopes = [part for part in row.scopes.split(" ") if part]
        return {
            "connected": True,
            "user_email": row.user_email,
            "scopes": scopes,
            "last_synced_at": row.last_synced_at.isoformat() if row.last_synced_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    def _deserialize_payload(self, row: GoogleDriveUserCredential) -> dict:
        raw = self.crypto.decrypt(row.token_encrypted)
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise RuntimeError("Stored Google Drive credential payload is invalid.")
        return payload

    def get_stored_payload(self, user_email: str) -> dict | None:
        row = self._row_for(user_email)
        if not row:
            return None
        return self._deserialize_payload(row)

    def _build_google_credentials(self, payload: dict) -> Credentials:
        scopes: list[str] | None = None
        scope_raw = payload.get("scope") or payload.get("scopes")
        if isinstance(scope_raw, str) and scope_raw.strip():
            scopes = [part for part in scope_raw.split(" ") if part.strip()]
        elif isinstance(scope_raw, list):
            scopes = [str(item).strip() for item in scope_raw if str(item).strip()]

        expiry = None
        expiry_raw = payload.get("expiry")
        if isinstance(expiry_raw, str) and expiry_raw.strip():
            try:
                parsed = datetime.fromisoformat(expiry_raw.replace("Z", "+00:00"))
                expiry = _normalize_expiry_for_google(parsed)
            except ValueError:
                expiry = None

        creds = Credentials(
            token=payload.get("access_token"),
            refresh_token=payload.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.settings.google_drive_client_id,
            client_secret=self.settings.google_drive_client_secret,
            scopes=scopes or ["https://www.googleapis.com/auth/drive.readonly"],
        )
        if expiry is not None:
            creds.expiry = expiry
        return creds

    def get_google_credentials(self, user_email: str) -> Credentials:
        row = self._row_for(user_email)
        if not row:
            raise RuntimeError("Google Drive is not connected for this user.")

        payload = self._deserialize_payload(row)
        creds = self._build_google_credentials(payload)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            payload["access_token"] = creds.token
            payload["refresh_token"] = creds.refresh_token or payload.get("refresh_token")
            payload["scope"] = " ".join(creds.scopes) if creds.scopes else payload.get("scope")
            if creds.expiry:
                normalized_expiry = _normalize_expiry_for_google(creds.expiry)
                payload["expiry"] = normalized_expiry.isoformat() if normalized_expiry else None
            self.upsert_token_payload(row.user_email, payload, commit=True)
        return creds

    def update_last_synced(self, user_email: str) -> None:
        row = self._row_for(user_email)
        if not row:
            return
        row.last_synced_at = _utcnow()
        row.updated_at = _utcnow()
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)

    @staticmethod
    def token_payload_from_oauth_exchange(payload: dict) -> dict:
        now = _utcnow()
        now_naive = now.astimezone(timezone.utc).replace(tzinfo=None)
        expires_in = payload.get("expires_in")
        expiry = None
        if isinstance(expires_in, (int, float)) and expires_in > 0:
            expiry = (now_naive + timedelta(seconds=float(expires_in))).isoformat()
        return {
            "access_token": payload.get("access_token"),
            "refresh_token": payload.get("refresh_token"),
            "scope": payload.get("scope", ""),
            "token_type": payload.get("token_type", "Bearer"),
            "expiry": expiry,
            "obtained_at": now.isoformat(),
        }
