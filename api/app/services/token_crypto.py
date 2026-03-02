from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.settings import get_settings


class TokenCrypto:
    def __init__(self) -> None:
        settings = get_settings()
        configured = (settings.google_drive_token_encryption_key or "").strip()
        if configured:
            key = self._normalize_key(configured)
        else:
            # Dev-safe fallback to avoid blocking local setup; set GOOGLE_DRIVE_TOKEN_ENCRYPTION_KEY in production.
            seed = (
                f"{settings.app_name}|"
                f"{settings.google_drive_client_secret or ''}|"
                f"{settings.feishu_app_secret or ''}|dev-only"
            )
            key = base64.urlsafe_b64encode(hashlib.sha256(seed.encode("utf-8")).digest())
        self._fernet = Fernet(key)

    @staticmethod
    def _normalize_key(value: str) -> bytes:
        raw = value.encode("utf-8")
        try:
            decoded = base64.urlsafe_b64decode(raw)
            if len(decoded) == 32:
                return raw
        except Exception:
            pass
        digest = hashlib.sha256(raw).digest()
        return base64.urlsafe_b64encode(digest)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise RuntimeError("Unable to decrypt stored OAuth credential.") from exc
