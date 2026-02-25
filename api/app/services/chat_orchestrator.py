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
        matches = sum(1 for term in terms if cls._contains_term(lowered, term))
        return matches / max(1, len(terms))

    def _rerank_oracle_hits(self, query: str, hits: list) -> list:
        if not hits:
            return hits
        critical = {
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
        }
        query_terms = self._query_terms(query)

        def score(hit) -> float:
            body = f"{hit.title}\n{hit.text[:1500]}"
            overlap = self._lexical_overlap(body, query)
            lowered = body.lower()
            matched_critical = sum(
                1 for t in query_terms if t in critical and self._contains_term(lowered, t)
            )
            nav_penalty = 0.0
            title = (hit.title or "").lower()
            if title.endswith("/toc.md") or title.endswith("toc.md") or title.endswith("_index.md"):
                nav_penalty -= 0.30
            if title.endswith("/overview.md") or title.endswith("overview.md") or title.endswith("glossary.md"):
                nav_penalty -= 0.16
            if title in {"overview", "glossary", "toc"}:
                nav_penalty -= 0.18
            source_boost = 0.08 if hit.source_type == SourceType.TIDB_DOCS_ONLINE.value else 0.0
            return (0.42 * hit.score) + (0.58 * overlap) + min(0.24, matched_critical * 0.08) + source_boost + nav_penalty

        ranked = sorted(hits, key=score, reverse=True)
        return ranked

    def _oracle_high_quality_hits(self, query: str, hits: list) -> list:
        if not hits:
            return []
        focus_terms = {
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
        }
        query_terms = self._query_terms(query)
        query_focus = [term for term in query_terms if term in focus_terms]
        required_focus = 1
        if "replication" in query_focus and "lag" in query_focus:
            required_focus = 3
        filtered = []
        for hit in hits:
            body = f"{hit.title}\n{hit.text[:1600]}".lower()
            overlap = self._lexical_overlap(body, query)
            if overlap < 0.16:
                continue
            if query_focus:
                matched_focus = sum(1 for term in query_focus if self._contains_term(body, term))
                if "tiflash" in query_focus and not self._contains_term(body, "tiflash"):
                    continue
                if matched_focus < required_focus:
                    continue
            filtered.append(hit)
        return filtered

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
            online_hits = self.docs_retriever.search(rewritten, max_results=5)
            hits = hits + online_hits
            hits = self._rerank_oracle_hits(message, hits)
            high_quality = self._oracle_high_quality_hits(message, hits)
            hits = (high_quality or hits)[:resolved_top_k]

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
            for hit in hits[:8]
        ]

        if mode == "call_assistant":
            data = self.llm.answer_call_assistant(message, hits, model=llm_model, tools=llm_tools)
            data["citations"] = citations
            return data, self.retriever.retrieval_payload(hits, resolved_top_k)

        data = self.llm.answer_oracle(message, hits, model=llm_model, tools=llm_tools)
        data["citations"] = citations
        return data, self.retriever.retrieval_payload(hits, resolved_top_k)
    @staticmethod
    def _contains_term(haystack: str, term: str) -> bool:
        pattern = rf"(?<![a-z0-9_]){re.escape(term)}(?![a-z0-9_])"
        return re.search(pattern, haystack) is not None
