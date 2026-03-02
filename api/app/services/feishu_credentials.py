from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models import FeishuUserCredential
from app.services.token_crypto import TokenCrypto


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_expiry(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class FeishuCredentialService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.crypto = TokenCrypto()

    @staticmethod
    def _normalize_email(email: str) -> str:
        return (email or "").strip().lower()

    def _row_for(self, user_email: str) -> FeishuUserCredential | None:
        normalized = self._normalize_email(user_email)
        if not normalized:
            return None
        return self.db.execute(
            select(FeishuUserCredential).where(FeishuUserCredential.user_email == normalized)
        ).scalar_one_or_none()

    def row_for_user(self, user_email: str) -> FeishuUserCredential | None:
        return self._row_for(user_email)

    def upsert_token_payload(self, user_email: str, payload: dict, *, commit: bool = True) -> FeishuUserCredential:
        normalized = self._normalize_email(user_email)
        if not normalized:
            raise RuntimeError("A valid user email is required for Feishu credentials.")

        row = self._row_for(normalized)
        if row is None:
            row = FeishuUserCredential(user_email=normalized, token_encrypted="", scopes=None)

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

    def _deserialize_payload(self, row: FeishuUserCredential) -> dict:
        raw = self.crypto.decrypt(row.token_encrypted)
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise RuntimeError("Stored Feishu credential payload is invalid.")
        return payload

    def get_stored_payload(self, user_email: str) -> dict | None:
        row = self._row_for(user_email)
        if not row:
            return None
        return self._deserialize_payload(row)

    @staticmethod
    def _oauth_headers(app_id: str, app_secret: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {app_id}:{app_secret}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def _call_refresh(self, payload: dict, *, app_id: str, app_secret: str, base_url: str) -> dict:
        if not app_id or not app_secret:
            raise RuntimeError("Feishu app credentials are required to refresh user access tokens.")

        headers = self._oauth_headers(app_id, app_secret)
        refresh_body = {
            "grant_type": "refresh_token",
            "refresh_token": payload.get("refresh_token"),
        }
        refresh_paths = [
            "/authen/v1/oidc/refresh_access_token",
            "/authen/v1/refresh_access_token",
        ]

        errors: list[str] = []
        for path in refresh_paths:
            try:
                res = httpx.post(f"{base_url.rstrip('/')}{path}", headers=headers, json=refresh_body, timeout=20.0)
                if res.status_code >= 400:
                    errors.append(f"{path}:HTTP{res.status_code}")
                    continue
                body = res.json()
                if body.get("code") != 0:
                    errors.append(f"{path}:{body.get('msg') or body.get('code')}")
                    continue
                data = body.get("data") or {}
                if data.get("access_token"):
                    return data
            except Exception as exc:
                errors.append(f"{path}:{exc}")
        raise RuntimeError(f"Failed to refresh Feishu user token ({'; '.join(errors)})")

    def get_access_token(
        self,
        user_email: str,
        *,
        app_id: str,
        app_secret: str,
        base_url: str | None = None,
    ) -> str:
        row = self._row_for(user_email)
        if not row:
            raise RuntimeError("Feishu is not connected for this user.")

        payload = self._deserialize_payload(row)
        access_token = str(payload.get("access_token") or "").strip()
        refresh_token = str(payload.get("refresh_token") or "").strip()
        expiry = _parse_expiry(payload.get("expiry"))
        now = _utcnow()

        should_refresh = not access_token
        if expiry and expiry <= (now + timedelta(seconds=60)):
            should_refresh = True

        if should_refresh and refresh_token:
            refreshed = self._call_refresh(
                payload,
                app_id=app_id,
                app_secret=app_secret,
                base_url=base_url or self.settings.feishu_base_url,
            )
            new_payload = self.token_payload_from_oauth_exchange(refreshed)
            if not new_payload.get("refresh_token"):
                new_payload["refresh_token"] = refresh_token
            self.upsert_token_payload(row.user_email, new_payload, commit=True)
            access_token = str(new_payload.get("access_token") or "").strip()

        if not access_token:
            raise RuntimeError("Feishu user token is missing or expired. Reconnect Feishu OAuth.")
        return access_token

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
        expires_in = payload.get("expires_in")
        expiry = None
        if isinstance(expires_in, (int, float)) and expires_in > 0:
            expiry = (now + timedelta(seconds=float(expires_in))).isoformat()
        return {
            "access_token": payload.get("access_token"),
            "refresh_token": payload.get("refresh_token"),
            "scope": payload.get("scope") or payload.get("scopes") or "",
            "token_type": payload.get("token_type", "Bearer"),
            "expiry": expiry,
            "obtained_at": now.isoformat(),
        }
