from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from openai import OpenAI

from app.core.settings import get_settings
from app.prompts.templates import SYSTEM_CALL_COACH, SYSTEM_ORACLE
from app.retrieval.types import RetrievedChunk
from app.utils.redaction import redact_sensitive_text


class LLMService:
    def __init__(self, api_key: str | None = None) -> None:
        self.settings = get_settings()
        self.model = self.settings.openai_model
        self._validate_enterprise_settings()
        self.clients: list[OpenAI] = []
        self._register_clients(api_key)
        if not self.clients and self.settings.security_fail_closed_on_missing_llm_key:
            raise RuntimeError("OPENAI_API_KEY is required by security policy for LLM calls.")

    def _register_clients(self, request_api_key: str | None) -> None:
        seen: set[str] = set()
        for key in [request_api_key, self.settings.openai_api_key]:
            if not key or key in seen:
                continue
            seen.add(key)
            kwargs: dict = {"api_key": key}
            if self.settings.openai_base_url:
                kwargs["base_url"] = self.settings.openai_base_url
            self.clients.append(OpenAI(**kwargs))

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

    def _responses_json(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        tools: list[dict] | None = None,
    ) -> dict[str, Any] | None:
        if not self.clients:
            return None
        import logging
        logger = logging.getLogger(__name__)
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
                logger.warning("LLM call failed (%s: %s) — trying next path", type(exc).__name__, exc)
                continue

        return None

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

    def answer_oracle(self, message: str, hits: list[RetrievedChunk], *, model: str | None = None, tools: list[dict] | None = None) -> dict[str, Any]:
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
        llm = self._responses_json(SYSTEM_ORACLE, prompt, model=model, tools=tools)
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

    def answer_call_assistant(self, message: str, hits: list[RetrievedChunk], *, model: str | None = None, tools: list[dict] | None = None) -> dict[str, Any]:
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
        llm = self._responses_json(SYSTEM_CALL_COACH, prompt, model=model, tools=tools)
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
