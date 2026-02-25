from __future__ import annotations

import hashlib
import math
from typing import Iterable
from urllib.parse import urlparse

from openai import OpenAI

from app.core.settings import get_settings
from app.utils.redaction import redact_sensitive_text


class EmbeddingService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._validate_enterprise_settings()
        if self.settings.openai_api_key:
            self.client = OpenAI(api_key=self.settings.openai_api_key, base_url=self.settings.openai_base_url)
        else:
            self.client = None
            if self.settings.security_fail_closed_on_missing_embedding_key:
                raise RuntimeError("OPENAI_API_KEY is required by security policy for embedding calls.")
        self.dim = self.settings.embedding_dimensions

    def _validate_enterprise_settings(self) -> None:
        base_url = self.settings.openai_base_url

        if self.settings.security_require_private_llm_endpoint and not base_url:
            raise RuntimeError("OPENAI_BASE_URL is required by security policy.")

        if not base_url:
            return

        parsed = urlparse(base_url)
        if not parsed.scheme or not parsed.netloc:
            raise RuntimeError("OPENAI_BASE_URL must be a valid absolute URL.")

        if parsed.scheme.lower() != "https" and not self.settings.security_allow_insecure_http_llm:
            raise RuntimeError("OPENAI_BASE_URL must use HTTPS unless explicitly allowed.")

        if not self.settings.is_allowed_llm_base_url(base_url):
            raise RuntimeError("OPENAI_BASE_URL is not in SECURITY_ALLOWED_LLM_BASE_URLS.")

    def _hash_embedding(self, text: str) -> list[float]:
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        for i in range(self.dim):
            b = seed[i % len(seed)]
            values.append((b / 255.0) * 2 - 1)
        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values]

    def embed(self, text: str) -> list[float]:
        payload = redact_sensitive_text(text) if self.settings.security_redact_before_llm else text
        if not self.client:
            return self._hash_embedding(payload)

        response = self.client.embeddings.create(model=self.settings.openai_embedding_model, input=payload)
        vector = response.data[0].embedding
        if len(vector) < self.dim:
            vector = vector + [0.0] * (self.dim - len(vector))
        return vector[: self.dim]

    def batch_embed(self, texts: Iterable[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]
