from __future__ import annotations

import base64
import json
from pathlib import Path

from app.core.settings import get_settings
from app.services.llm import LLMService


def _jwt(payload: dict) -> str:
    header = {"alg": "none", "typ": "JWT"}
    encode = lambda data: base64.urlsafe_b64encode(json.dumps(data).encode("utf-8")).decode("utf-8").rstrip("=")
    return f"{encode(header)}.{encode(payload)}.sig"


def test_extract_account_id_from_jwt():
    token = _jwt({"https://api.openai.com/auth": {"chatgpt_account_id": "acct_123"}})
    assert LLMService._extract_account_id_from_jwt(token) == "acct_123"


def test_codex_model_falls_back_to_codex_variant():
    assert LLMService._resolve_codex_model("gpt-4.1", "gpt-4.1") == "gpt-5.3-codex"
    assert LLMService._resolve_codex_model("gpt-5.3-codex", "gpt-4.1") == "gpt-5.3-codex"


def test_loads_codex_credential_from_auth_json(monkeypatch, tmp_path: Path):
    codex_home = tmp_path / ".codex"
    codex_home.mkdir(parents=True, exist_ok=True)
    auth_path = codex_home / "auth.json"
    token = _jwt({"https://api.openai.com/auth": {"chatgpt_account_id": "acct_abc"}})
    auth_path.write_text(
        json.dumps(
            {
                "last_refresh": "2026-02-25T12:00:00Z",
                "tokens": {
                    "access_token": token,
                    "refresh_token": "refresh_xyz",
                    "account_id": "acct_abc",
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()

    service = LLMService()
    assert len(service.codex_credentials) >= 1
    assert service.codex_credentials[0].account_id == "acct_abc"
    assert service.codex_credentials[0].refresh_token == "refresh_xyz"

    get_settings.cache_clear()


def test_responses_text_uses_codex_fallback(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    service = LLMService()
    monkeypatch.setattr(
        service,
        "_call_codex_responses_text",
        lambda **kwargs: "codex-answer",
    )

    text = service._responses_text("sys", "hello")
    assert text == "codex-answer"

    get_settings.cache_clear()
