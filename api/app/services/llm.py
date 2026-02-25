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
        effective_key = api_key or self.settings.openai_api_key
        if effective_key:
            kwargs: dict = {"api_key": effective_key}
            if self.settings.openai_base_url:
                kwargs["base_url"] = self.settings.openai_base_url
            self.client = OpenAI(**kwargs)
        else:
            self.client = None
            if self.settings.security_fail_closed_on_missing_llm_key:
                raise RuntimeError("OPENAI_API_KEY is required by security policy for LLM calls.")

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
    def _short_quote(text: str, max_words: int = 25) -> str:
        words = re.sub(r"\s+", " ", text).strip().split(" ")
        return " ".join(words[:max_words]).strip()

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
        if not self.client:
            return None
        import logging
        logger = logging.getLogger(__name__)
        try:
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
            response = self.client.responses.create(**kwargs)
            payload = next(
                (item.content[0].text for item in response.output if item.type == "message"),
                "{}",
            )
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                return None
        except Exception as exc:
            logger.warning("LLM call failed (%s: %s) — using fallback response", type(exc).__name__, exc)
            return None

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
                "answer": (
                    "The AI model could not generate a response. "
                    "Please check that your ChatGPT OAuth session is active (Settings -> ChatGPT Account) "
                    "or configure an OpenAI API key."
                ),
                "citations": [],
                "follow_up_questions": [],
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
