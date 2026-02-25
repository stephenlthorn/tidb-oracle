from __future__ import annotations

import pytest

from app.core.settings import get_settings
from app.services.embedding import EmbeddingService
from app.services.llm import LLMService
from app.utils.redaction import redact_payload, redact_sensitive_text


def test_redaction_masks_common_sensitive_fields():
    text = "Email me at rep@pingcap.com, call +1 415-555-1212, card 4111 1111 1111 1111"
    out = redact_sensitive_text(text)
    assert "[REDACTED_EMAIL]" in out
    assert "[REDACTED_PHONE]" in out
    assert "[REDACTED_CARD]" in out


def test_redact_payload_recurses():
    payload = {
        "user": "rep@pingcap.com",
        "nested": [{"contact": "+1 415-555-1212"}],
    }
    out = redact_payload(payload)
    assert out["user"] == "[REDACTED_EMAIL]"
    assert out["nested"][0]["contact"] == "[REDACTED_PHONE]"


def test_llm_fail_closed_when_api_key_missing(monkeypatch):
    monkeypatch.setenv("SECURITY_FAIL_CLOSED_ON_MISSING_LLM_KEY", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://llm.pingcap.internal")
    monkeypatch.setenv("SECURITY_ALLOWED_LLM_BASE_URLS", "https://llm.pingcap.internal")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        LLMService()

    get_settings.cache_clear()


def test_embedding_rejects_unapproved_llm_endpoint(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com")
    monkeypatch.setenv("SECURITY_ALLOWED_LLM_BASE_URLS", "https://llm.pingcap.internal")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="SECURITY_ALLOWED_LLM_BASE_URLS"):
        EmbeddingService()

    get_settings.cache_clear()
