from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.models import KBConfig, SourceType
from app.retrieval.service import HybridRetriever
from app.retrieval.tidb_docs import TiDBDocsRetriever
from app.services.llm import LLMService
from app.services.query_rewrite import QueryRewriter
from app.utils.email_utils import is_internal_email


class ChatOrchestrator:
    def __init__(self, db: Session, openai_token: str | None = None) -> None:
        self.db = db
        self.settings = get_settings()
        self.retriever = HybridRetriever(db)
        self.docs_retriever = TiDBDocsRetriever()
        self.llm = LLMService(api_key=openai_token)
        self.rewriter = QueryRewriter()

    def _guardrail_external_messaging(self, text: str) -> str | None:
        lowered = text.lower()
        if "email" not in lowered and "send" not in lowered and "slack" not in lowered:
            return None

        emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
        for email in emails:
            if not is_internal_email(email, self.settings.domain_allowlist):
                return "I cannot help send or draft external outbound messages. Policy allows internal recipients only (@pingcap.com)."
        return None

    @staticmethod
    def _citation_quote(text: str) -> str:
        words = re.sub(r"\s+", " ", text).strip().split()
        return " ".join(words[:25])

    def _resolve_top_k(self, kb_config: KBConfig | None, request_top_k: int) -> int:
        if kb_config is not None:
            return kb_config.retrieval_top_k
        return self.settings.retrieval_top_k

    @staticmethod
    def _resolve_allowed_sources(kb_config: KBConfig | None, mode: str) -> list[str] | None:
        if mode == "oracle":
            if kb_config is None:
                return [SourceType.GOOGLE_DRIVE.value, SourceType.FEISHU.value]
            allowed: list[str] = []
            if kb_config.google_drive_enabled:
                allowed.append(SourceType.GOOGLE_DRIVE.value)
            if kb_config.feishu_enabled:
                allowed.append(SourceType.FEISHU.value)
            return allowed or [SourceType.GOOGLE_DRIVE.value]
        # call_assistant and any other modes: use Chorus only
        if kb_config is None:
            return None
        allowed = []
        if kb_config.chorus_enabled:
            allowed.append(SourceType.CHORUS.value)
        return allowed or None

    @staticmethod
    def _resolve_llm_config(
        kb_config: KBConfig | None,
        settings: Settings,
        mode: str,
    ) -> tuple[str, list[dict]]:
        model = (kb_config.llm_model if kb_config else None) or settings.openai_model
        tools: list[dict] = []
        if mode == "oracle":
            # Always enable web search for oracle — LLM fetches TiDB docs when needed.
            tools.append({"type": "web_search_preview"})
        elif kb_config and kb_config.web_search_enabled:
            tools.append({"type": "web_search_preview"})
        if kb_config and kb_config.code_interpreter_enabled:
            tools.append({"type": "code_interpreter", "container": {"type": "auto"}})
        return model, tools

    def run(self, *, mode: str, user: str, message: str, top_k: int, filters: dict, context: dict) -> tuple[dict, dict]:
        blocked = self._guardrail_external_messaging(message)
        if blocked:
            payload = {
                "answer": blocked,
                "citations": [],
                "follow_up_questions": ["Do you want an internal-only draft to @pingcap.com recipients instead?"],
            }
            return payload, {"top_k": 0, "results": []}

        kb_config: KBConfig | None = self.db.get(KBConfig, 1)
        resolved_top_k = self._resolve_top_k(kb_config, top_k)
        allowed_sources = self._resolve_allowed_sources(kb_config, mode)
        llm_model, llm_tools = self._resolve_llm_config(kb_config, self.settings, mode)

        mode_filters = dict(filters or {})
        requested_sources = [str(s).lower() for s in (mode_filters.get("source_type") or [])]
        if mode == "oracle":
            oracle_allowed = allowed_sources or [SourceType.GOOGLE_DRIVE.value, SourceType.FEISHU.value]
            if requested_sources:
                filtered = [source for source in requested_sources if source in set(oracle_allowed)]
                mode_filters["source_type"] = filtered or oracle_allowed
            else:
                mode_filters["source_type"] = oracle_allowed
        elif mode == "call_assistant":
            mode_filters["source_type"] = allowed_sources or [SourceType.CHORUS.value]

        rewritten = self.rewriter.rewrite(message, mode)
        hits = self.retriever.search(rewritten, top_k=resolved_top_k, filters=mode_filters)
        if mode == "oracle":
            online_hits = self.docs_retriever.search(rewritten, max_results=3)
            hits = hits + online_hits

        citations = [
            {
                "title": hit.title,
                "source_type": hit.source_type,
                "source_id": hit.source_id,
                "chunk_id": hit.chunk_id,
                "quote": self._citation_quote(hit.text),
                "relevance": hit.score,
                "file_id": hit.file_id,
                "timestamp": hit.metadata.get("start_time_sec"),
            }
            for hit in hits
        ]

        if mode == "call_assistant":
            data = self.llm.answer_call_assistant(message, hits, model=llm_model, tools=llm_tools)
            data["citations"] = citations
            return data, self.retriever.retrieval_payload(hits, resolved_top_k)

        data = self.llm.answer_oracle(message, hits, model=llm_model, tools=llm_tools)
        data["citations"] = citations
        return data, self.retriever.retrieval_payload(hits, resolved_top_k)
