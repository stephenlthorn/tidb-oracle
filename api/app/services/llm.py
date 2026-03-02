from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
import platform
from pathlib import Path
import re
import subprocess
from typing import Any
from urllib.parse import urlparse

import httpx
from openai import OpenAI

from app.core.settings import get_settings
from app.prompts.personas import get_persona_label, normalize_persona
from app.prompts.templates import (
    SYSTEM_CALL_COACH,
    SYSTEM_MARKETING_EXECUTION,
    SYSTEM_MARKET_RESEARCH,
    SYSTEM_ORACLE,
    SYSTEM_REP_EXECUTION,
    SYSTEM_SE_EXECUTION,
)
from app.retrieval.types import RetrievedChunk
from app.utils.redaction import redact_sensitive_text


JWT_CLAIM_PATH = "https://api.openai.com/auth"
CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_TOKEN_URL = "https://auth.openai.com/oauth/token"
DEFAULT_CODEX_BASE_URL = "https://chatgpt.com/backend-api"


@dataclass
class CodexCredential:
    access_token: str
    refresh_token: str | None = None
    account_id: str | None = None
    expires_at_ms: int | None = None
    source: str = "unknown"


class LLMService:
    def __init__(self, api_key: str | None = None) -> None:
        self.settings = get_settings()
        self.model = self.settings.openai_model
        self.logger = logging.getLogger(__name__)
        self.disable_codex_auth = os.getenv("DISABLE_CODEX_AUTH", "").strip().lower() in {"1", "true", "yes", "on"}
        self._validate_enterprise_settings()
        self.clients: list[OpenAI] = []
        self._openai_client_keys: set[str] = set()
        self.codex_credentials: list[CodexCredential] = []
        self.last_error: str | None = None
        self._register_clients(api_key)
        if not self.clients and self.settings.security_fail_closed_on_missing_llm_key:
            raise RuntimeError("OPENAI_API_KEY is required by security policy for LLM calls.")

    def _register_clients(self, request_api_key: str | None) -> None:
        if request_api_key:
            if self._is_jwt_token(request_api_key):
                self._add_codex_credential(
                    CodexCredential(
                        access_token=request_api_key.strip(),
                        account_id=self._extract_account_id_from_jwt(request_api_key.strip()),
                        source="request",
                    )
                )
            else:
                self._register_openai_client(request_api_key)

        if self.settings.openai_api_key:
            self._register_openai_client(self.settings.openai_api_key)

        if not self.disable_codex_auth:
            payload, api_key, auth_credential = self._load_codex_auth_state()
            if api_key:
                self._register_openai_client(api_key)
            if auth_credential:
                self._add_codex_credential(auth_credential)

            keychain_credential = self._load_codex_keychain_credential()
            if keychain_credential:
                self._add_codex_credential(keychain_credential)

    @staticmethod
    def _is_jwt_token(value: str) -> bool:
        token = value.strip()
        parts = token.split(".")
        return len(parts) == 3 and all(parts)

    def _register_openai_client(self, key: str) -> None:
        normalized = key.strip()
        if not normalized:
            return
        if normalized in self._openai_client_keys:
            return
        kwargs: dict[str, Any] = {"api_key": normalized}
        if self.settings.openai_base_url:
            kwargs["base_url"] = self.settings.openai_base_url
        self.clients.append(OpenAI(**kwargs))
        self._openai_client_keys.add(normalized)

    def _add_codex_credential(self, credential: CodexCredential) -> None:
        if not credential.access_token:
            return
        if any(c.access_token == credential.access_token for c in self.codex_credentials):
            return
        self.codex_credentials.append(credential)

    @staticmethod
    def _resolve_codex_home_path() -> Path:
        configured = os.getenv("CODEX_HOME")
        home = Path(configured).expanduser() if configured else (Path.home() / ".codex")
        try:
            return home.resolve()
        except Exception:
            return home

    @classmethod
    def _resolve_codex_auth_path(cls) -> Path:
        return cls._resolve_codex_home_path() / "auth.json"

    @staticmethod
    def _safe_json_load(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
        return {}

    @staticmethod
    def _parse_epoch_ms(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            if value <= 0:
                return None
            if value > 1_000_000_000_000:
                return int(value)
            if value > 1_000_000_000:
                return int(value * 1000)
            return None
        if isinstance(value, str):
            parsed = value.strip()
            if not parsed:
                return None
            if parsed.isdigit():
                return LLMService._parse_epoch_ms(int(parsed))
            try:
                dt = datetime.fromisoformat(parsed.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return int(dt.timestamp() * 1000)
            except ValueError:
                return None
        return None

    @classmethod
    def _extract_account_id_from_jwt(cls, token: str) -> str | None:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        padding = "=" * (-len(payload_b64) % 4)
        try:
            raw = base64.urlsafe_b64decode(payload_b64 + padding)
            payload = json.loads(raw.decode("utf-8"))
            auth = payload.get(JWT_CLAIM_PATH, {})
            account_id = auth.get("chatgpt_account_id") if isinstance(auth, dict) else None
            return account_id if isinstance(account_id, str) and account_id.strip() else None
        except Exception:
            return None

    @classmethod
    def _build_codex_credential(cls, payload: dict[str, Any], source: str) -> CodexCredential | None:
        tokens = payload.get("tokens") if isinstance(payload.get("tokens"), dict) else None
        access = tokens.get("access_token") if tokens else None
        if not isinstance(access, str) or not access.strip():
            return None

        refresh = tokens.get("refresh_token") if isinstance(tokens.get("refresh_token"), str) else None
        account_id = tokens.get("account_id") if isinstance(tokens.get("account_id"), str) else None
        if not account_id:
            account_id = cls._extract_account_id_from_jwt(access)

        last_refresh_ms = cls._parse_epoch_ms(payload.get("last_refresh"))
        expires_at_ms = (last_refresh_ms + 60 * 60 * 1000) if last_refresh_ms else None
        return CodexCredential(
            access_token=access.strip(),
            refresh_token=refresh.strip() if isinstance(refresh, str) and refresh.strip() else None,
            account_id=account_id.strip() if isinstance(account_id, str) and account_id.strip() else None,
            expires_at_ms=expires_at_ms,
            source=source,
        )

    @classmethod
    def _load_codex_auth_state(cls) -> tuple[dict[str, Any], str | None, CodexCredential | None]:
        auth_path = cls._resolve_codex_auth_path()
        if not auth_path.exists():
            return {}, None, None
        payload = cls._safe_json_load(auth_path)
        key = payload.get("OPENAI_API_KEY")
        api_key = key.strip() if isinstance(key, str) and key.strip() else None
        credential = cls._build_codex_credential(payload, source="auth_json")
        return payload, api_key, credential

    @classmethod
    def _load_codex_keychain_credential(cls) -> CodexCredential | None:
        if platform.system().lower() != "darwin":
            return None

        codex_home = str(cls._resolve_codex_home_path())
        account_hash = hashlib.sha256(codex_home.encode("utf-8")).hexdigest()[:16]
        account = f"cli|{account_hash}"
        cmd = ["security", "find-generic-password", "-s", "Codex Auth", "-a", account, "-w"]
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception:
            return None

        raw = (result.stdout or "").strip()
        if not raw:
            return None
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return cls._build_codex_credential(payload, source="keychain")
        except Exception:
            return None
        return None

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

    def _sanitize_for_provider(self, text: str) -> str:
        if not self.settings.security_redact_before_llm:
            return text
        return redact_sensitive_text(text)

    @staticmethod
    def _contains_term(haystack: str, term: str) -> bool:
        pattern = rf"(?<![a-z0-9_]){re.escape(term)}(?![a-z0-9_])"
        return re.search(pattern, haystack) is not None

    @staticmethod
    def _short_quote(text: str, max_words: int = 25) -> str:
        words = re.sub(r"\s+", " ", text).strip().split(" ")
        return " ".join(words[:max_words]).strip()

    @staticmethod
    def _query_terms(query: str) -> list[str]:
        tokens = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9._-]{1,}", query.lower())
        stop = {
            "what",
            "where",
            "when",
            "which",
            "who",
            "why",
            "how",
            "are",
            "the",
            "for",
            "and",
            "with",
            "from",
            "into",
            "this",
            "that",
            "your",
            "ours",
            "their",
            "about",
            "should",
            "could",
            "would",
            "please",
            "show",
            "tell",
            "give",
        }
        seen: set[str] = set()
        terms: list[str] = []
        for token in tokens:
            if len(token) < 3 or token in stop:
                continue
            if token not in seen:
                terms.append(token)
                seen.add(token)
        return terms

    @classmethod
    def _lexical_overlap(cls, text: str, query: str) -> float:
        terms = cls._query_terms(query)
        if not terms:
            return 0.0
        lowered = text.lower()
        hits = sum(1 for term in terms if cls._contains_term(lowered, term))
        return hits / max(1, len(terms))

    @staticmethod
    def _fallback_followups(mode: str) -> list[str]:
        if mode == "oracle":
            return [
                "What workload patterns and p95/p99 latency targets matter most?",
                "Do they need HTAP now or in a later phase?",
                "What is the expected growth, ingest rate, and retention window?",
                "What online DDL operations are frequent and business critical?",
            ]
        return [
            "Which risks are time-critical before the next meeting?",
            "What evidence is still missing from the transcript?",
            "Which decision criteria did the customer prioritize most?",
        ]

    @staticmethod
    def _compose_persona_system_prompt(
        base_prompt: str,
        persona_name: str | None,
        persona_prompt: str | None,
    ) -> str:
        prompt = (persona_prompt or "").strip()
        if not prompt:
            return base_prompt
        normalized = normalize_persona(persona_name)
        label = get_persona_label(normalized)
        return (
            f"{base_prompt}\n\n"
            "Persona guidance:\n"
            f"- Target user persona: {label}\n"
            "- Adapt tone and recommendations for this persona while preserving policy and grounding.\n"
            f"- Persona prompt: {prompt}"
        )

    def _resolve_codex_responses_url(self) -> str:
        configured = (self.settings.openai_base_url or "").strip()
        raw_base = configured if "chatgpt.com" in configured else DEFAULT_CODEX_BASE_URL
        normalized = raw_base.rstrip("/")
        if normalized.endswith("/codex/responses"):
            return normalized
        if normalized.endswith("/codex"):
            return f"{normalized}/responses"
        return f"{normalized}/codex/responses"

    @staticmethod
    def _resolve_codex_model(model: str | None, default_model: str) -> str:
        candidate = (model or default_model or "").strip()
        if candidate and "codex" in candidate.lower():
            return candidate
        return "gpt-5.3-codex"

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any] | None:
        raw = text.strip()
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass

        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end <= start:
            return None
        candidate = raw[start : end + 1]
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _dedupe_repeated_text(text: str) -> str:
        normalized = text.strip()
        n = len(normalized)
        if n > 0 and n % 2 == 0:
            half = n // 2
            if normalized[:half] == normalized[half:]:
                return normalized[:half].strip()
        return normalized

    @staticmethod
    def _extract_text_from_response_payload(payload: dict[str, Any] | None) -> str | None:
        if not payload:
            return None

        output_text = payload.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        output = payload.get("output")
        if not isinstance(output, list):
            return None
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()
        return None

    @staticmethod
    def _parse_codex_error(raw: str, status: int) -> str:
        text = raw.strip()
        if not text:
            return f"Codex request failed with status {status}."
        try:
            payload = json.loads(text)
            err = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(err, dict):
                msg = err.get("message")
                if isinstance(msg, str) and msg.strip():
                    return msg.strip()
        except Exception:
            pass
        return text[:600]

    def _persist_codex_auth_state(self, credential: CodexCredential) -> None:
        auth_path = self._resolve_codex_auth_path()
        payload = self._safe_json_load(auth_path) if auth_path.exists() else {}
        tokens = payload.get("tokens") if isinstance(payload.get("tokens"), dict) else {}
        tokens["access_token"] = credential.access_token
        if credential.refresh_token:
            tokens["refresh_token"] = credential.refresh_token
        if credential.account_id:
            tokens["account_id"] = credential.account_id
        payload["tokens"] = tokens
        payload["last_refresh"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        auth_path.parent.mkdir(parents=True, exist_ok=True)
        auth_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _refresh_codex_credential(self, credential: CodexCredential) -> CodexCredential | None:
        if not credential.refresh_token:
            return None
        try:
            response = httpx.post(
                CODEX_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": credential.refresh_token,
                    "client_id": CODEX_CLIENT_ID,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=20.0,
            )
        except Exception as exc:
            self.last_error = f"Codex refresh failed: {type(exc).__name__}: {exc}"
            return None

        if response.status_code >= 400:
            self.last_error = f"Codex refresh failed: {response.status_code} {response.text[:400]}"
            return None

        try:
            payload = response.json()
        except Exception as exc:
            self.last_error = f"Codex refresh JSON parse failed: {type(exc).__name__}: {exc}"
            return None

        access = payload.get("access_token")
        refresh = payload.get("refresh_token")
        expires_in = payload.get("expires_in")
        if not isinstance(access, str) or not access.strip():
            self.last_error = "Codex refresh failed: missing access_token."
            return None
        if not isinstance(refresh, str) or not refresh.strip():
            refresh = credential.refresh_token

        expires_at_ms: int | None = None
        if isinstance(expires_in, (int, float)) and expires_in > 0:
            expires_at_ms = int(datetime.now(timezone.utc).timestamp() * 1000 + (float(expires_in) * 1000))

        refreshed = CodexCredential(
            access_token=access.strip(),
            refresh_token=refresh.strip() if isinstance(refresh, str) and refresh.strip() else None,
            account_id=self._extract_account_id_from_jwt(access.strip()) or credential.account_id,
            expires_at_ms=expires_at_ms,
            source=credential.source,
        )
        try:
            self._persist_codex_auth_state(refreshed)
        except Exception:
            pass
        return refreshed

    def _codex_request_once(
        self,
        credential: CodexCredential,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None,
        tools: list[dict] | None,
    ) -> tuple[str | None, int]:
        account_id = credential.account_id or self._extract_account_id_from_jwt(credential.access_token)
        if not account_id:
            raise RuntimeError("Codex token is missing chatgpt_account_id claim.")

        payload: dict[str, Any] = {
            "model": self._resolve_codex_model(model, self.model),
            "store": False,
            "stream": True,
            "instructions": system_prompt,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_prompt}],
                }
            ],
            "text": {"verbosity": "medium"},
            "include": ["reasoning.encrypted_content"],
        }

        headers = {
            "Authorization": f"Bearer {credential.access_token}",
            "chatgpt-account-id": account_id,
            "OpenAI-Beta": "responses=experimental",
            "originator": "tidb-oracle",
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        }

        url = self._resolve_codex_responses_url()
        with httpx.stream("POST", url, headers=headers, json=payload, timeout=90.0) as response:
            status = response.status_code
            if status >= 400:
                raw = response.read().decode("utf-8", errors="ignore")
                self.last_error = self._parse_codex_error(raw, status)
                return None, status

            text_chunks: list[str] = []
            completed_payload: dict[str, Any] | None = None
            data_lines: list[str] = []

            def consume_event(lines: list[str]) -> bool:
                nonlocal completed_payload
                raw_event = "\n".join(lines).strip()
                if not raw_event or raw_event == "[DONE]":
                    return False
                try:
                    event = json.loads(raw_event)
                except Exception:
                    return False
                if not isinstance(event, dict):
                    return False

                event_type = event.get("type")
                if event_type == "response.output_text.delta":
                    delta = event.get("delta")
                    if isinstance(delta, str) and delta:
                        text_chunks.append(delta)
                elif event_type in {"response.output_text.done", "response.output_text"}:
                    text = event.get("text")
                    if isinstance(text, str) and text.strip() and not text_chunks:
                        text_chunks.append(text)
                elif event_type in {"response.done", "response.completed"}:
                    response_payload = event.get("response")
                    if isinstance(response_payload, dict):
                        completed_payload = response_payload
                    return True
                elif event_type == "response.failed":
                    err = event.get("response", {}).get("error") if isinstance(event.get("response"), dict) else {}
                    msg = err.get("message") if isinstance(err, dict) else None
                    raise RuntimeError(msg if isinstance(msg, str) and msg.strip() else "Codex response failed.")
                elif event_type == "error":
                    msg = event.get("message")
                    raise RuntimeError(msg if isinstance(msg, str) and msg.strip() else "Codex request failed.")
                return False

            for raw_line in response.iter_lines():
                line = raw_line.strip()
                if not line:
                    if data_lines:
                        if consume_event(data_lines):
                            break
                        data_lines = []
                    continue
                if line.startswith("data:"):
                    data_lines.append(line[5:].strip())

            if data_lines:
                consume_event(data_lines)

        text = "".join(text_chunks).strip()
        if text:
            return self._dedupe_repeated_text(text), status

        fallback = self._extract_text_from_response_payload(completed_payload)
        if fallback:
            return self._dedupe_repeated_text(fallback), status
        return None, status

    def _call_codex_responses_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None,
        tools: list[dict] | None,
    ) -> str | None:
        if not self.codex_credentials:
            return None

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        for idx, original in enumerate(list(self.codex_credentials)):
            credential = original
            for attempt in range(2):
                if (
                    credential.refresh_token
                    and credential.expires_at_ms is not None
                    and credential.expires_at_ms <= now_ms + 120_000
                ):
                    refreshed = self._refresh_codex_credential(credential)
                    if refreshed:
                        credential = refreshed
                        self.codex_credentials[idx] = refreshed

                try:
                    text, status = self._codex_request_once(
                        credential,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        model=model,
                        tools=tools,
                    )
                except Exception as exc:
                    self.last_error = f"Codex request failed: {type(exc).__name__}: {exc}"
                    text, status = None, 0

                if text and text.strip():
                    return text.strip()

                if status not in {401, 403} or attempt == 1 or not credential.refresh_token:
                    break

                refreshed = self._refresh_codex_credential(credential)
                if not refreshed:
                    break
                credential = refreshed
                self.codex_credentials[idx] = refreshed

        return None

    def _responses_json(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        tools: list[dict] | None = None,
    ) -> dict[str, Any] | None:
        safe_user_prompt = self._sanitize_for_provider(user_prompt)
        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": safe_user_prompt},
            ],
            "text": {"format": {"type": "json_object"}},
        }
        if tools:
            kwargs["tools"] = tools

        for client in self.clients:
            try:
                response = client.responses.create(**kwargs)
                payload = next(
                    (item.content[0].text for item in response.output if item.type == "message"),
                    "{}",
                )
                try:
                    return json.loads(payload)
                except json.JSONDecodeError:
                    return None
            except Exception as exc:
                self.logger.warning("LLM call failed (%s: %s) — trying next path", type(exc).__name__, exc)
                self.last_error = f"{type(exc).__name__}: {exc}"
                continue

        codex_text = self._call_codex_responses_text(
            system_prompt=system_prompt,
            user_prompt=safe_user_prompt,
            model=model,
            tools=tools,
        )
        if codex_text:
            return self._extract_json_object(codex_text)
        return None

    def _responses_text(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        tools: list[dict] | None = None,
    ) -> str | None:
        safe_user_prompt = self._sanitize_for_provider(user_prompt)
        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": safe_user_prompt},
            ],
        }
        if tools:
            kwargs["tools"] = tools

        for client in self.clients:
            try:
                response = client.responses.create(**kwargs)
                output_text = getattr(response, "output_text", None)
                if output_text and isinstance(output_text, str) and output_text.strip():
                    return output_text.strip()

                for item in getattr(response, "output", []) or []:
                    if getattr(item, "type", "") != "message":
                        continue
                    for content in getattr(item, "content", []) or []:
                        text = getattr(content, "text", None)
                        if text and isinstance(text, str) and text.strip():
                            return text.strip()
            except Exception as exc:
                self.logger.warning("LLM text call failed (%s: %s) — trying next path", type(exc).__name__, exc)
                self.last_error = f"{type(exc).__name__}: {exc}"
                continue

        return self._call_codex_responses_text(
            system_prompt=system_prompt,
            user_prompt=safe_user_prompt,
            model=model,
            tools=tools,
        )

    def _local_oracle_synthesis(self, message: str, hits: list[RetrievedChunk]) -> str:
        focus_vocab = {
            "tiflash",
            "tikv",
            "htap",
            "replication",
            "lag",
            "aurora",
            "mysql",
            "mpp",
            "ddl",
            "migration",
            "poc",
            "tso",
        }
        query_terms = self._query_terms(message)
        focus_terms = [term for term in query_terms if term in focus_vocab or any(ch.isdigit() for ch in term)]
        required_matches = 2
        if "replication" in focus_terms and "lag" in focus_terms:
            required_matches = 3

        def focus_matches(hit: RetrievedChunk) -> int:
            hay = f"{hit.title}\n{hit.text[:1800]}".lower()
            return sum(1 for term in focus_terms if self._contains_term(hay, term))

        ranked = sorted(
            hits,
            key=lambda h: self._lexical_overlap(f"{h.title}\n{h.text}", message)
            + (0.15 if h.source_type == "tidb_docs_online" else 0.0)
            + min(0.10, max(0.0, h.score / 10.0)),
            reverse=True,
        )
        top: list[RetrievedChunk] = []
        for hit in ranked:
            overlap = self._lexical_overlap(f"{hit.title}\n{hit.text}", message)
            if overlap < 0.15:
                continue
            if focus_terms:
                matched = focus_matches(hit)
                if "tiflash" in focus_terms and not self._contains_term(f"{hit.title}\n{hit.text}".lower(), "tiflash"):
                    continue
                if matched < required_matches:
                    continue
            top.append(hit)
            if len(top) >= 3:
                break
        evidence = [
            f"- {self._short_quote(h.text, max_words=22)}."
            for h in top
            if h.text and h.text.strip()
        ]
        if not evidence:
            return (
                "I couldn't reach the configured LLM right now, and I don't yet have strong evidence that matches this exact question. "
                "Try adding specifics like TiDB version, TiFlash replica count, write rate, and freshness SLO."
            )
        if len(evidence) < 2:
            return (
                "I could only find partial evidence for this question while the LLM is unavailable.\n"
                + "\n".join(evidence)
                + "\n\nTo answer replication-lag characteristics accurately, add details such as TiDB version, TiFlash replica count, write rate, and freshness SLO."
            )
        return (
            "LLM is currently unavailable, so here is a grounded synthesis from retrieved sources:\n"
            + "\n".join(evidence)
            + "\n\n"
            f"Based on this evidence, a practical next step is to validate this against the exact ask: \"{message}\"."
        )

    def answer_oracle(
        self,
        message: str,
        hits: list[RetrievedChunk],
        *,
        model: str | None = None,
        tools: list[dict] | None = None,
        allow_ungrounded: bool = False,
        persona_name: str | None = None,
        persona_prompt: str | None = None,
    ) -> dict[str, Any]:
        system_prompt = self._compose_persona_system_prompt(SYSTEM_ORACLE, persona_name, persona_prompt)
        if allow_ungrounded:
            prompt = f"User question:\n{message}\n\nProvide a concise, high-quality answer."
            answer = self._responses_text(system_prompt, prompt, model=model, tools=tools)
            if answer:
                return {"answer": answer, "follow_up_questions": self._fallback_followups("oracle")}
            err = self.last_error or "No provider credentials configured."
            return {
                "answer": (
                    "LLM unavailable for direct Oracle chat. "
                    "Set `OPENAI_API_KEY` in `/Users/stephen/Documents/New project/.env` "
                    "or connect ChatGPT OAuth again at http://localhost:3000/login "
                    "(Codex auth is also read from ~/.codex/auth.json). "
                    f"Latest error: {err}"
                ),
                "citations": [],
                "follow_up_questions": [],
            }

        if not hits:
            return {
                "answer": (
                    "I don't have enough context to answer this question. "
                    "Make sure Google Drive and Feishu are synced in Admin settings. "
                    "You can also try rephrasing your question."
                ),
                "citations": [],
                "follow_up_questions": [
                    "Is Google Drive synced? (Admin -> Sync Google Drive)",
                    "Is Feishu configured with a folder token?",
                ],
            }

        context = "\n\n".join(
            [
                f"[{h.source_id}:{h.chunk_id}] {h.text[:1200]}"
                for h in hits[:8]
            ]
        )
        prompt = (
            "Question:\n"
            f"{message}\n\n"
            "Evidence:\n"
            f"{context}\n\n"
            "Return JSON with keys: answer (string), follow_up_questions (array of 3-7 strings)."
        )
        llm = self._responses_json(system_prompt, prompt, model=model, tools=tools)
        if llm and isinstance(llm.get("answer"), str):
            followups = llm.get("follow_up_questions") or self._fallback_followups("oracle")
            return {"answer": llm["answer"], "follow_up_questions": followups[:7]}
        if llm is None:
            return {
                "answer": self._local_oracle_synthesis(message, hits),
                "citations": [],
                "follow_up_questions": self._fallback_followups("oracle"),
            }

        return {
            "answer": (
                "The AI model returned an unexpected response format. "
                "Please retry the request or check your model/tool configuration."
            ),
            "citations": [],
            "follow_up_questions": self._fallback_followups("oracle"),
        }

    def answer_call_assistant(
        self,
        message: str,
        hits: list[RetrievedChunk],
        *,
        model: str | None = None,
        tools: list[dict] | None = None,
        persona_name: str | None = None,
        persona_prompt: str | None = None,
    ) -> dict[str, Any]:
        system_prompt = self._compose_persona_system_prompt(SYSTEM_CALL_COACH, persona_name, persona_prompt)
        if not hits:
            return {
                "what_happened": ["Insufficient transcript evidence retrieved."],
                "risks": ["Need the call id or transcript context to proceed."],
                "next_steps": ["Provide the target `chorus_call_id` and relevant account context."],
                "questions_to_ask_next_call": self._fallback_followups("call_assistant"),
            }

        context = "\n\n".join([f"[{h.source_id}:{h.chunk_id}] {h.text[:1500]}" for h in hits[:8]])
        prompt = (
            f"User request: {message}\n\n"
            "Transcript/Internal evidence:\n"
            f"{context}\n\n"
            "Return JSON with keys: what_happened, risks, next_steps, questions_to_ask_next_call (all arrays of concise strings)."
        )
        llm = self._responses_json(system_prompt, prompt, model=model, tools=tools)
        if llm and all(k in llm for k in ["what_happened", "risks", "next_steps", "questions_to_ask_next_call"]):
            return {
                "what_happened": list(llm.get("what_happened", []))[:6],
                "risks": list(llm.get("risks", []))[:6],
                "next_steps": list(llm.get("next_steps", []))[:7],
                "questions_to_ask_next_call": list(llm.get("questions_to_ask_next_call", []))[:7],
            }

        return {
            "what_happened": [self._short_quote(h.text, max_words=22) for h in hits[:3]],
            "risks": ["Clarify workload priority and success criteria.", "Verify competitive comparison assumptions with hard metrics."],
            "next_steps": ["Collect top query set with latencies.", "Align on a focused POC plan and measurement rubric."],
            "questions_to_ask_next_call": self._fallback_followups("call_assistant"),
        }

    def answer_market_research(
        self,
        *,
        strategic_goal: str,
        regions: list[str],
        current_customers: list[dict[str, str]],
        pipeline: list[dict[str, str]],
        additional_context: str,
        top_n: int,
        model: str | None = None,
        persona_name: str | None = "sales_representative",
        persona_prompt: str | None = None,
        required_inputs: list[str] | None = None,
    ) -> dict[str, Any] | None:
        system_prompt = self._compose_persona_system_prompt(
            SYSTEM_MARKET_RESEARCH,
            persona_name,
            persona_prompt,
        )

        prompt = (
            "Build a strategic account execution list for this rep request.\n\n"
            f"Goal: {strategic_goal}\n"
            f"Regions: {regions}\n"
            f"Top accounts requested: {top_n}\n"
            f"Current customers: {json.dumps(current_customers)}\n"
            f"Pipeline: {json.dumps(pipeline)}\n"
            f"Additional context: {additional_context}\n\n"
            "Return strict JSON with keys:\n"
            "- summary (string)\n"
            "- required_inputs (array of strings)\n"
            "- priority_accounts (array of objects with: "
            "account, motion_type, region, priority, why_now, actions, suggested_assets)\n"
            "- execution_plan (array of strings)\n"
        )

        llm = self._responses_json(system_prompt, prompt, model=model, tools=None)
        if not isinstance(llm, dict):
            return None

        summary = llm.get("summary")
        required = llm.get("required_inputs")
        accounts = llm.get("priority_accounts")
        execution = llm.get("execution_plan")

        if not isinstance(summary, str):
            return None
        if not isinstance(required, list):
            required = required_inputs or []
        if not isinstance(execution, list):
            execution = []
        if not isinstance(accounts, list):
            return None

        normalized_accounts: list[dict[str, Any]] = []
        for raw in accounts[:top_n]:
            if not isinstance(raw, dict):
                continue
            account = raw.get("account")
            if not isinstance(account, str) or not account.strip():
                continue
            motion_type = raw.get("motion_type") if isinstance(raw.get("motion_type"), str) else "pipeline"
            region = raw.get("region") if isinstance(raw.get("region"), str) else "Unknown"
            priority = raw.get("priority") if isinstance(raw.get("priority"), str) else "Medium"
            why_now = raw.get("why_now") if isinstance(raw.get("why_now"), str) else ""
            actions = raw.get("actions") if isinstance(raw.get("actions"), list) else []
            assets = raw.get("suggested_assets") if isinstance(raw.get("suggested_assets"), list) else []
            normalized_accounts.append(
                {
                    "account": account.strip(),
                    "motion_type": motion_type.strip() or "pipeline",
                    "region": region.strip() or "Unknown",
                    "priority": priority.strip() or "Medium",
                    "why_now": why_now.strip() or "Prioritized based on available territory data.",
                    "actions": [str(item).strip() for item in actions if str(item).strip()][:5],
                    "suggested_assets": [str(item).strip() for item in assets if str(item).strip()][:4],
                }
            )

        if not normalized_accounts:
            return None

        return {
            "summary": summary.strip(),
            "required_inputs": [str(item).strip() for item in required if str(item).strip()],
            "priority_accounts": normalized_accounts,
            "execution_plan": [str(item).strip() for item in execution if str(item).strip()][:6],
        }

    @staticmethod
    def _normalize_string_list(value: Any, *, limit: int, item_limit: int = 240) -> list[str]:
        if not isinstance(value, list):
            return []
        out: list[str] = []
        for item in value:
            text = str(item).strip()
            if not text:
                continue
            out.append(text[:item_limit])
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _normalize_risk_items(value: Any, *, limit: int) -> list[dict[str, str]]:
        if not isinstance(value, list):
            return []
        out: list[dict[str, str]] = []
        for raw in value[:limit]:
            if not isinstance(raw, dict):
                continue
            severity = str(raw.get("severity") or "medium").strip().lower()
            if severity not in {"low", "medium", "high"}:
                severity = "medium"
            signal = str(raw.get("signal") or "").strip()
            impact = str(raw.get("impact") or "").strip()
            mitigation = str(raw.get("mitigation") or "").strip()
            if not signal:
                continue
            out.append(
                {
                    "severity": severity,
                    "signal": signal[:220],
                    "impact": (impact or "Deal progression risk if unaddressed.")[:220],
                    "mitigation": (mitigation or "Assign owner and due date on next account review.")[:220],
                }
            )
        return out

    def answer_rep_account_brief(
        self,
        *,
        account: str,
        ask: str,
        hits: list[RetrievedChunk],
        model: str | None = None,
        persona_name: str | None = "sales_representative",
        persona_prompt: str | None = None,
    ) -> dict[str, Any] | None:
        system_prompt = self._compose_persona_system_prompt(SYSTEM_REP_EXECUTION, persona_name, persona_prompt)
        context = "\n\n".join([f"[{h.source_id}:{h.chunk_id}] {h.text[:1200]}" for h in hits[:8]])
        prompt = (
            f"Account: {account}\n"
            f"Request: {ask}\n"
            f"Evidence:\n{context}\n\n"
            "Return strict JSON with keys:\n"
            "- summary (string)\n"
            "- business_context (array of strings)\n"
            "- decision_criteria (array of strings)\n"
            "- recommended_assets (array of strings)\n"
            "- next_meeting_agenda (array of strings)\n"
        )
        llm = self._responses_json(system_prompt, prompt, model=model)
        if not isinstance(llm, dict) or not isinstance(llm.get("summary"), str):
            return None
        return {
            "summary": llm["summary"].strip(),
            "business_context": self._normalize_string_list(llm.get("business_context"), limit=6),
            "decision_criteria": self._normalize_string_list(llm.get("decision_criteria"), limit=6),
            "recommended_assets": self._normalize_string_list(llm.get("recommended_assets"), limit=6),
            "next_meeting_agenda": self._normalize_string_list(llm.get("next_meeting_agenda"), limit=7),
        }

    def answer_rep_discovery_questions(
        self,
        *,
        account: str,
        ask: str,
        hits: list[RetrievedChunk],
        count: int,
        model: str | None = None,
        persona_name: str | None = "sales_representative",
        persona_prompt: str | None = None,
    ) -> dict[str, Any] | None:
        system_prompt = self._compose_persona_system_prompt(SYSTEM_REP_EXECUTION, persona_name, persona_prompt)
        context = "\n\n".join([f"[{h.source_id}:{h.chunk_id}] {h.text[:1200]}" for h in hits[:8]])
        prompt = (
            f"Account: {account}\n"
            f"Request: {ask}\n"
            f"Questions requested: {count}\n"
            f"Evidence:\n{context}\n\n"
            "Return strict JSON with keys:\n"
            "- questions (array of strings)\n"
            "- intent (array of strings with rationale for each question)\n"
        )
        llm = self._responses_json(system_prompt, prompt, model=model)
        if not isinstance(llm, dict):
            return None
        questions = self._normalize_string_list(llm.get("questions"), limit=count)
        if len(questions) < 3:
            return None
        return {
            "questions": questions,
            "intent": self._normalize_string_list(llm.get("intent"), limit=count),
        }

    def answer_rep_follow_up_draft(
        self,
        *,
        account: str,
        ask: str,
        to_recipients: list[str],
        cc_recipients: list[str],
        hits: list[RetrievedChunk],
        tone: str,
        model: str | None = None,
        persona_name: str | None = "sales_representative",
        persona_prompt: str | None = None,
    ) -> dict[str, Any] | None:
        system_prompt = self._compose_persona_system_prompt(SYSTEM_REP_EXECUTION, persona_name, persona_prompt)
        context = "\n\n".join([f"[{h.source_id}:{h.chunk_id}] {h.text[:1200]}" for h in hits[:8]])
        prompt = (
            f"Account: {account}\n"
            f"Request: {ask}\n"
            f"Tone: {tone}\n"
            f"To: {to_recipients}\n"
            f"CC: {cc_recipients}\n"
            f"Evidence:\n{context}\n\n"
            "Return strict JSON with keys:\n"
            "- subject (string)\n"
            "- body (string)\n"
            "- key_points (array of strings)\n"
        )
        llm = self._responses_json(system_prompt, prompt, model=model)
        if not isinstance(llm, dict):
            return None
        subject = llm.get("subject")
        body = llm.get("body")
        if not isinstance(subject, str) or not subject.strip():
            return None
        if not isinstance(body, str) or not body.strip():
            return None
        return {
            "subject": subject.strip()[:180],
            "body": body.strip(),
            "key_points": self._normalize_string_list(llm.get("key_points"), limit=6),
        }

    def answer_rep_deal_risk(
        self,
        *,
        account: str,
        ask: str,
        hits: list[RetrievedChunk],
        model: str | None = None,
        persona_name: str | None = "sales_representative",
        persona_prompt: str | None = None,
    ) -> dict[str, Any] | None:
        system_prompt = self._compose_persona_system_prompt(SYSTEM_REP_EXECUTION, persona_name, persona_prompt)
        context = "\n\n".join([f"[{h.source_id}:{h.chunk_id}] {h.text[:1200]}" for h in hits[:8]])
        prompt = (
            f"Account: {account}\n"
            f"Request: {ask}\n"
            f"Evidence:\n{context}\n\n"
            "Return strict JSON with keys:\n"
            "- risk_level (one of: low, medium, high)\n"
            "- risks (array of objects: severity, signal, impact, mitigation)\n"
            "- action_plan (array of strings)\n"
        )
        llm = self._responses_json(system_prompt, prompt, model=model)
        if not isinstance(llm, dict):
            return None
        risks = self._normalize_risk_items(llm.get("risks"), limit=8)
        if not risks:
            return None
        risk_level = str(llm.get("risk_level") or "medium").strip().lower()
        if risk_level not in {"low", "medium", "high"}:
            risk_level = "medium"
        return {
            "risk_level": risk_level,
            "risks": risks,
            "action_plan": self._normalize_string_list(llm.get("action_plan"), limit=8),
        }

    def answer_se_poc_plan(
        self,
        *,
        account: str,
        ask: str,
        hits: list[RetrievedChunk],
        target_offering: str,
        model: str | None = None,
        persona_name: str | None = "se",
        persona_prompt: str | None = None,
    ) -> dict[str, Any] | None:
        system_prompt = self._compose_persona_system_prompt(SYSTEM_SE_EXECUTION, persona_name, persona_prompt)
        context = "\n\n".join([f"[{h.source_id}:{h.chunk_id}] {h.text[:1200]}" for h in hits[:8]])
        prompt = (
            f"Account: {account}\n"
            f"Target offering: {target_offering}\n"
            f"Request: {ask}\n"
            f"Evidence:\n{context}\n\n"
            "Return strict JSON with keys:\n"
            "- readiness_score (integer 0-100)\n"
            "- readiness_summary (string)\n"
            "- gaps (array of strings)\n"
            "- workplan (array of strings)\n"
            "- success_criteria (array of strings)\n"
            "- status (string: ready|conditional|blocked)\n"
        )
        llm = self._responses_json(system_prompt, prompt, model=model)
        if not isinstance(llm, dict):
            return None
        summary = llm.get("readiness_summary")
        if not isinstance(summary, str) or not summary.strip():
            return None
        score_raw = llm.get("readiness_score")
        try:
            score = int(score_raw)
        except Exception:
            return None
        score = max(0, min(100, score))
        status = str(llm.get("status") or "conditional").strip().lower()
        if status not in {"ready", "conditional", "blocked"}:
            status = "conditional"
        return {
            "readiness_score": score,
            "readiness_summary": summary.strip(),
            "gaps": self._normalize_string_list(llm.get("gaps"), limit=8),
            "workplan": self._normalize_string_list(llm.get("workplan"), limit=10),
            "success_criteria": self._normalize_string_list(llm.get("success_criteria"), limit=8),
            "status": status,
        }

    def answer_se_poc_readiness(
        self,
        *,
        account: str,
        ask: str,
        hits: list[RetrievedChunk],
        model: str | None = None,
        persona_name: str | None = "se",
        persona_prompt: str | None = None,
    ) -> dict[str, Any] | None:
        system_prompt = self._compose_persona_system_prompt(SYSTEM_SE_EXECUTION, persona_name, persona_prompt)
        context = "\n\n".join([f"[{h.source_id}:{h.chunk_id}] {h.text[:1200]}" for h in hits[:8]])
        prompt = (
            f"Account: {account}\n"
            f"Request: {ask}\n"
            f"Evidence:\n{context}\n\n"
            "Return strict JSON with keys:\n"
            "- readiness_score (integer 0-100)\n"
            "- readiness_summary (string)\n"
            "- blockers (array of strings)\n"
            "- required_inputs (array of strings)\n"
            "- status (string: ready|conditional|blocked)\n"
        )
        llm = self._responses_json(system_prompt, prompt, model=model)
        if not isinstance(llm, dict):
            return None
        summary = llm.get("readiness_summary")
        if not isinstance(summary, str) or not summary.strip():
            return None
        try:
            score = int(llm.get("readiness_score"))
        except Exception:
            return None
        status = str(llm.get("status") or "conditional").strip().lower()
        if status not in {"ready", "conditional", "blocked"}:
            status = "conditional"
        return {
            "readiness_score": max(0, min(100, score)),
            "readiness_summary": summary.strip(),
            "blockers": self._normalize_string_list(llm.get("blockers"), limit=8),
            "required_inputs": self._normalize_string_list(llm.get("required_inputs"), limit=8),
            "status": status,
        }

    def answer_se_architecture_fit(
        self,
        *,
        account: str,
        ask: str,
        hits: list[RetrievedChunk],
        model: str | None = None,
        persona_name: str | None = "se",
        persona_prompt: str | None = None,
    ) -> dict[str, Any] | None:
        system_prompt = self._compose_persona_system_prompt(SYSTEM_SE_EXECUTION, persona_name, persona_prompt)
        context = "\n\n".join([f"[{h.source_id}:{h.chunk_id}] {h.text[:1200]}" for h in hits[:8]])
        prompt = (
            f"Account: {account}\n"
            f"Request: {ask}\n"
            f"Evidence:\n{context}\n\n"
            "Return strict JSON with keys:\n"
            "- fit_summary (string)\n"
            "- strong_fit_for (array of strings)\n"
            "- watchouts (array of strings)\n"
            "- migration_path (array of strings)\n"
        )
        llm = self._responses_json(system_prompt, prompt, model=model)
        if not isinstance(llm, dict):
            return None
        fit_summary = llm.get("fit_summary")
        if not isinstance(fit_summary, str) or not fit_summary.strip():
            return None
        return {
            "fit_summary": fit_summary.strip(),
            "strong_fit_for": self._normalize_string_list(llm.get("strong_fit_for"), limit=7),
            "watchouts": self._normalize_string_list(llm.get("watchouts"), limit=7),
            "migration_path": self._normalize_string_list(llm.get("migration_path"), limit=8),
        }

    def answer_se_competitor_coach(
        self,
        *,
        account: str,
        ask: str,
        competitor: str,
        hits: list[RetrievedChunk],
        model: str | None = None,
        persona_name: str | None = "se",
        persona_prompt: str | None = None,
    ) -> dict[str, Any] | None:
        system_prompt = self._compose_persona_system_prompt(SYSTEM_SE_EXECUTION, persona_name, persona_prompt)
        context = "\n\n".join([f"[{h.source_id}:{h.chunk_id}] {h.text[:1200]}" for h in hits[:8]])
        prompt = (
            f"Account: {account}\n"
            f"Competitor: {competitor}\n"
            f"Request: {ask}\n"
            f"Evidence:\n{context}\n\n"
            "Return strict JSON with keys:\n"
            "- competitor (string)\n"
            "- positioning (array of strings)\n"
            "- proof_points (array of strings)\n"
            "- landmines (array of strings)\n"
            "- discovery_questions (array of strings)\n"
        )
        llm = self._responses_json(system_prompt, prompt, model=model)
        if not isinstance(llm, dict):
            return None
        resolved_competitor = str(llm.get("competitor") or competitor).strip()
        return {
            "competitor": resolved_competitor or competitor,
            "positioning": self._normalize_string_list(llm.get("positioning"), limit=8),
            "proof_points": self._normalize_string_list(llm.get("proof_points"), limit=8),
            "landmines": self._normalize_string_list(llm.get("landmines"), limit=8),
            "discovery_questions": self._normalize_string_list(llm.get("discovery_questions"), limit=8),
        }

    def answer_marketing_intelligence(
        self,
        *,
        ask: str,
        regions: list[str],
        verticals: list[str],
        hits: list[RetrievedChunk],
        model: str | None = None,
        persona_name: str | None = "marketing_specialist",
        persona_prompt: str | None = None,
    ) -> dict[str, Any] | None:
        system_prompt = self._compose_persona_system_prompt(SYSTEM_MARKETING_EXECUTION, persona_name, persona_prompt)
        context = "\n\n".join([f"[{h.source_id}:{h.chunk_id}] {h.text[:1200]}" for h in hits[:10]])
        prompt = (
            f"Request: {ask}\n"
            f"Regions: {regions}\n"
            f"Verticals: {verticals}\n"
            f"Evidence:\n{context}\n\n"
            "Return strict JSON with keys:\n"
            "- summary (string)\n"
            "- top_signals (array of strings)\n"
            "- campaign_angles (array of strings)\n"
            "- priority_accounts (array of strings)\n"
            "- next_actions (array of strings)\n"
        )
        llm = self._responses_json(system_prompt, prompt, model=model)
        if not isinstance(llm, dict):
            return None
        summary = llm.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            return None
        return {
            "summary": summary.strip(),
            "top_signals": self._normalize_string_list(llm.get("top_signals"), limit=8),
            "campaign_angles": self._normalize_string_list(llm.get("campaign_angles"), limit=8),
            "priority_accounts": self._normalize_string_list(llm.get("priority_accounts"), limit=8),
            "next_actions": self._normalize_string_list(llm.get("next_actions"), limit=8),
        }
