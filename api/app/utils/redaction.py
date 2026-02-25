from __future__ import annotations

import re
from typing import Any

EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_PATTERN = re.compile(r"(?<!\w)\+?\d(?:[\d .()\-/]{7,}\d)")
CARD_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,19}\b")


def redact_sensitive_text(text: str) -> str:
    redacted = CARD_PATTERN.sub("[REDACTED_CARD]", text)
    redacted = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", redacted)
    redacted = PHONE_PATTERN.sub("[REDACTED_PHONE]", redacted)
    return redacted


def redact_payload(payload: Any) -> Any:
    if isinstance(payload, str):
        return redact_sensitive_text(payload)
    if isinstance(payload, list):
        return [redact_payload(item) for item in payload]
    if isinstance(payload, dict):
        return {str(key): redact_payload(value) for key, value in payload.items()}
    return payload
