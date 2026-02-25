from __future__ import annotations

from typing import Any

from app.services.llm import LLMService


class ArtifactGenerator:
    def __init__(self) -> None:
        self.llm = LLMService()

    def generate(self, normalized_transcript: dict[str, Any], supporting_snippets: list[str]) -> dict[str, Any]:
        call_id = normalized_transcript.get("chorus_call_id", "unknown")
        metadata = normalized_transcript.get("metadata", {})
        turns = normalized_transcript.get("turns", [])

        text_blob = "\n".join(turn.get("text", "") for turn in turns)
        lower = text_blob.lower()

        competitors = []
        for name in ["singlestore", "cockroachdb", "snowflake", "spanner"]:
            if name in lower:
                competitors.append(name.title())

        objections = []
        if "lag" in lower:
            objections.append("Concern about replication or query lag")
        if "ddl" in lower or "schema" in lower:
            objections.append("Wants confidence in online schema change behavior")
        if "cost" in lower:
            objections.append("Cost and footprint pressure")

        risks = [
            "Query mix and latency SLOs are not fully quantified.",
            "Sizing assumptions may drift without representative workload samples.",
        ]
        next_steps = [
            "Collect top 10 frequent and top 5 slowest queries with SLAs.",
            "Confirm ingest profile and ETL peak windows.",
            "Define a scoped POC success rubric with timeline and owners.",
        ]
        followups = [
            "Which query classes have strict p95/p99 latency requirements?",
            "What online DDL cadence is expected during peak periods?",
            "Is HTAP mandatory in phase 1 or can it be sequenced later?",
        ]

        support = "\n".join(supporting_snippets[:6])
        llm_result = self.llm.answer_call_assistant(
            "Generate concise SE coaching artifacts for this call.",
            [
                type("Obj", (), {"text": text_blob + "\n" + support, "source_id": call_id, "chunk_id": "artifact"})(),
            ],
        )

        summary = f"Call {call_id} ({metadata.get('account', 'unknown account')}): "
        summary += " ".join(llm_result.get("what_happened", [])[:2])

        recommended_collateral = [
            {
                "title": "TiDB Online DDL Best Practices",
                "drive_file_id": None,
                "reason": "Addresses schema-change concerns highlighted in the call.",
            },
            {
                "title": "TiDB HTAP & TiFlash Overview",
                "drive_file_id": None,
                "reason": "Helps align expectations for analytical workloads and latency tradeoffs.",
            },
        ]

        return {
            "summary": summary,
            "objections": objections or ["Need clearer evidence of blocker objections."],
            "competitors_mentioned": competitors,
            "risks": llm_result.get("risks", risks),
            "next_steps": llm_result.get("next_steps", next_steps),
            "recommended_collateral": recommended_collateral,
            "follow_up_questions": llm_result.get("questions_to_ask_next_call", followups),
            "model_info": {"provider": "openai", "model": self.llm.model, "prompt_hash": "static-v1"},
        }
