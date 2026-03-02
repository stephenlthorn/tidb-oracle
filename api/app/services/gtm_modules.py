from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditStatus,
    CallArtifact,
    ChorusCall,
    GTMAccountProfile,
    GTMGeneratedAsset,
    GTMModuleRun,
    GTMPOCPlan,
    GTMRiskSignal,
    GTMTrendInsight,
    KBConfig,
    OutboundMessage,
    SourceType,
)
from app.prompts.personas import get_default_persona_prompt, normalize_persona
from app.retrieval.service import HybridRetriever
from app.retrieval.types import RetrievedChunk
from app.services.llm import LLMService
from app.services.memory import MemoryService
from app.services.messaging import MessagingService
from app.utils.email_utils import is_internal_email
from app.utils.hashing import sha256_text


class GTMModuleService:
    def __init__(self, db: Session, openai_token: str | None = None) -> None:
        self.db = db
        self.retriever = HybridRetriever(db)
        self.llm = LLMService(api_key=openai_token)
        self.messaging = MessagingService(db)

    @staticmethod
    def _citation_quote(text: str) -> str:
        words = " ".join(text.split()).strip().split(" ")
        return " ".join(words[:25]).strip()

    @staticmethod
    def _dedupe_hits(hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        deduped: dict[str, RetrievedChunk] = {}
        for hit in hits:
            key = str(hit.chunk_id)
            existing = deduped.get(key)
            if existing is None or hit.score > existing.score:
                deduped[key] = hit
        return sorted(deduped.values(), key=lambda h: h.score, reverse=True)

    def _resolve_model(self) -> str | None:
        config: KBConfig | None = self.db.get(KBConfig, 1)
        return config.llm_model if config else None

    def module_enabled(self, key: str) -> bool:
        config: KBConfig | None = self.db.get(KBConfig, 1)
        if config is None:
            return True
        flags = config.feature_flags_json if isinstance(config.feature_flags_json, dict) else {}
        if key not in flags:
            return True
        return bool(flags.get(key))

    def _resolve_persona(self, default_persona: str) -> tuple[str, str]:
        config: KBConfig | None = self.db.get(KBConfig, 1)
        persona = normalize_persona(default_persona)
        prompt = get_default_persona_prompt(persona)
        if config and normalize_persona(config.persona_name) == persona and (config.persona_prompt or "").strip():
            prompt = config.persona_prompt.strip()
        return persona, prompt

    def _collect_hits(
        self,
        *,
        account: str,
        ask: str,
        user_email: str,
        chorus_call_id: str | None = None,
    ) -> list[RetrievedChunk]:
        viewer_email = (user_email or "").strip().lower()
        query = f"{account} {ask}".strip()

        doc_sources = [
            SourceType.GOOGLE_DRIVE.value,
            SourceType.FEISHU.value,
            SourceType.TIDB_DOCS_ONLINE.value,
            SourceType.MEMORY.value,
        ]
        doc_hits = self.retriever.search(
            query,
            top_k=6,
            filters={
                "source_type": doc_sources,
                "viewer_email": viewer_email,
            },
        )
        call_filters = {
            "source_type": [SourceType.CHORUS.value],
            "account": [account],
            "viewer_email": viewer_email,
        }
        call_query = query if not chorus_call_id else f"{query} {chorus_call_id}"
        call_hits = self.retriever.search(call_query, top_k=5, filters=call_filters)

        combined = self._dedupe_hits([*call_hits, *doc_hits])
        if combined:
            return combined[:10]

        fallback_hits = self.retriever.search(
            query,
            top_k=8,
            filters={"viewer_email": viewer_email},
        )
        return fallback_hits[:8]

    @staticmethod
    def _citations(hits: list[RetrievedChunk], limit: int = 8) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for hit in hits[:limit]:
            out.append(
                {
                    "title": hit.title,
                    "source_type": hit.source_type,
                    "source_id": hit.source_id,
                    "chunk_id": hit.chunk_id,
                    "quote": GTMModuleService._citation_quote(hit.text),
                    "relevance": hit.score,
                    "file_id": hit.file_id,
                    "timestamp": hit.metadata.get("start_time_sec"),
                }
            )
        return out

    def _latest_call(self, account: str, chorus_call_id: str | None) -> tuple[ChorusCall | None, CallArtifact | None]:
        if chorus_call_id:
            call = self.db.execute(
                select(ChorusCall).where(ChorusCall.chorus_call_id == chorus_call_id)
            ).scalar_one_or_none()
            if call is None:
                return None, None
            artifact = self.db.execute(
                select(CallArtifact)
                .where(CallArtifact.chorus_call_id == call.chorus_call_id)
                .order_by(CallArtifact.created_at.desc())
            ).scalars().first()
            return call, artifact

        calls = self.db.execute(select(ChorusCall).order_by(ChorusCall.date.desc())).scalars().all()
        call = next((row for row in calls if (row.account or "").strip().lower() == account.strip().lower()), None)
        if call is None:
            return None, None
        artifact = self.db.execute(
            select(CallArtifact)
            .where(CallArtifact.chorus_call_id == call.chorus_call_id)
            .order_by(CallArtifact.created_at.desc())
        ).scalars().first()
        return call, artifact

    def _record_module_run(
        self,
        *,
        module_name: str,
        actor: str,
        input_payload: dict[str, Any],
        retrieval_payload: dict[str, Any],
        output_payload: dict[str, Any],
        status: str,
        error_message: str | None = None,
    ) -> None:
        row = GTMModuleRun(
            module_name=module_name,
            actor=actor,
            input_json=input_payload,
            retrieval_json=retrieval_payload,
            output_json=output_payload,
            status=status,
            error_message=error_message,
        )
        self.db.add(row)
        self.db.commit()
        try:
            MemoryService(self.db).capture_interaction(
                actor=actor,
                mode=module_name,
                message=str(input_payload),
                response_payload=output_payload,
                retrieval_payload=retrieval_payload,
            )
        except Exception:
            self.db.rollback()

    def rep_account_brief(
        self,
        *,
        user: str,
        account: str,
        chorus_call_id: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        ask = "Build an execution-ready account brief for the rep."
        hits = self._collect_hits(account=account, ask=ask, user_email=user, chorus_call_id=chorus_call_id)
        model = self._resolve_model()
        persona_name, persona_prompt = self._resolve_persona("sales_representative")
        llm_payload = self.llm.answer_rep_account_brief(
            account=account,
            ask=ask,
            hits=hits,
            model=model,
            persona_name=persona_name,
            persona_prompt=persona_prompt,
        )

        if llm_payload is None:
            call, artifact = self._latest_call(account, chorus_call_id)
            summary = artifact.summary if artifact else (
                f"{account} is active and requires an updated discovery and validation plan before the next meeting."
            )
            business_context = [
                f"Current motion: {(call.stage if call else 'discovery').title() if (call and call.stage) else 'Discovery'}.",
                "Confirm decision process, timeline, and technical success criteria.",
            ]
            decision_criteria = [
                "Performance vs incumbent on representative query set.",
                "Operational simplicity and migration risk.",
                "Commercial fit and procurement timeline alignment.",
            ]
            recommended_assets = [
                "TiDB architecture one-pager for the current workload",
                "Competitor comparison sheet aligned to decision criteria",
                "POC checklist with milestone owners",
            ]
            next_meeting_agenda = [
                "Confirm top latency and throughput SLOs.",
                "Finalize technical validation scope and data set.",
                "Agree owner/date for each open blocker.",
            ]
            payload = {
                "account": account,
                "summary": summary,
                "business_context": business_context,
                "decision_criteria": decision_criteria,
                "recommended_assets": recommended_assets,
                "next_meeting_agenda": next_meeting_agenda,
                "citations": self._citations(hits),
            }
        else:
            payload = {
                "account": account,
                **llm_payload,
                "citations": self._citations(hits),
            }

        self.db.add(
            GTMAccountProfile(
                account=account,
                territory="East/Central",
                owner_email=user,
                metadata_json={
                    "summary": payload["summary"],
                    "decision_criteria": payload["decision_criteria"],
                },
            )
        )
        self.db.commit()

        retrieval = self.retriever.retrieval_payload(hits, 8)
        self._record_module_run(
            module_name="rep.account_brief",
            actor=user,
            input_payload={"account": account, "chorus_call_id": chorus_call_id},
            retrieval_payload=retrieval,
            output_payload={k: v for k, v in payload.items() if k != "citations"},
            status=AuditStatus.OK.value,
        )
        return payload, retrieval

    def rep_discovery_questions(
        self,
        *,
        user: str,
        account: str,
        chorus_call_id: str | None = None,
        count: int = 6,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        ask = "Generate sharp next-call discovery questions with intent."
        hits = self._collect_hits(account=account, ask=ask, user_email=user, chorus_call_id=chorus_call_id)
        model = self._resolve_model()
        persona_name, persona_prompt = self._resolve_persona("sales_representative")
        llm_payload = self.llm.answer_rep_discovery_questions(
            account=account,
            ask=ask,
            hits=hits,
            count=count,
            model=model,
            persona_name=persona_name,
            persona_prompt=persona_prompt,
        )

        if llm_payload is None:
            questions = [
                "Which 5 queries are tied to business-critical latency targets (p95/p99)?",
                "What daily ingest volume and peak write QPS must the target architecture sustain?",
                "Which schema changes occur most often and what impact is acceptable during business hours?",
                "Who has final technical sign-off and who controls budget approval timing?",
                "What proof would definitively disqualify the incumbent in this cycle?",
                "What must be true by the end of POC week 2 to continue investment?",
            ][:count]
            intent = [
                "Convert vague priorities into measurable acceptance criteria.",
                "Expose hidden scale constraints early.",
                "Surface operational risk tolerance before architecture commitments.",
                "Clarify stakeholder map and decision authority.",
                "Anchor competitive strategy to concrete evidence.",
                "Set milestone-based continuation gates.",
            ][:count]
            payload = {
                "account": account,
                "questions": questions,
                "intent": intent,
                "citations": self._citations(hits),
            }
        else:
            payload = {
                "account": account,
                **llm_payload,
                "citations": self._citations(hits),
            }

        retrieval = self.retriever.retrieval_payload(hits, 8)
        self._record_module_run(
            module_name="rep.discovery_questions",
            actor=user,
            input_payload={"account": account, "chorus_call_id": chorus_call_id, "count": count},
            retrieval_payload=retrieval,
            output_payload={k: v for k, v in payload.items() if k != "citations"},
            status=AuditStatus.OK.value,
        )
        return payload, retrieval

    def rep_follow_up_draft(
        self,
        *,
        user: str,
        account: str,
        chorus_call_id: str | None,
        requested_mode: str,
        to: list[str],
        cc: list[str],
        tone: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        ask = "Draft a concise internal follow-up note with actions and owners."
        call, artifact = self._latest_call(account, chorus_call_id)

        if not to:
            if call and call.rep_email:
                to = [call.rep_email]
            else:
                to = [user]
        if not cc and call and call.se_email:
            cc = [call.se_email]

        bad = [email for email in [*to, *cc] if not is_internal_email(email, self.messaging.settings.domain_allowlist)]
        if bad:
            row: OutboundMessage = self.messaging.draft_or_send(
                to=to,
                cc=cc,
                subject=f"{account} follow-up draft blocked",
                body="",
                requested_mode=requested_mode,
                chorus_call_id=(call.chorus_call_id if call else chorus_call_id),
                artifact_id=(artifact.id if artifact else None),
            )
            payload = {
                "account": account,
                "mode": row.mode.value,
                "subject": row.subject,
                "body": "",
                "to": row.to_recipients,
                "cc": row.cc_recipients,
                "reason_blocked": row.reason_blocked,
                "citations": [],
            }
            retrieval = {"top_k": 0, "results": []}
            self._record_module_run(
                module_name="rep.follow_up_draft",
                actor=user,
                input_payload={"account": account, "to": to, "cc": cc, "mode": requested_mode},
                retrieval_payload=retrieval,
                output_payload={k: v for k, v in payload.items() if k != "citations"},
                status=AuditStatus.OK.value,
            )
            return payload, retrieval

        hits = self._collect_hits(account=account, ask=ask, user_email=user, chorus_call_id=chorus_call_id)
        model = self._resolve_model()
        persona_name, persona_prompt = self._resolve_persona("sales_representative")
        llm_payload = self.llm.answer_rep_follow_up_draft(
            account=account,
            ask=ask,
            to_recipients=to,
            cc_recipients=cc,
            hits=hits,
            tone=tone,
            model=model,
            persona_name=persona_name,
            persona_prompt=persona_prompt,
        )

        if llm_payload is None:
            subject = self.messaging.build_email_subject(account)
            summary = artifact.summary if artifact else f"{account} review completed."
            next_steps = artifact.next_steps if artifact else ["Confirm next meeting date.", "Lock top 3 validation criteria."]
            questions = artifact.follow_up_questions if artifact else ["What decision gate is next?", "What blocker needs exec support?"]
            collateral = artifact.recommended_collateral if artifact else [{"title": "POC checklist", "reason": "Align success criteria"}]
            body = self.messaging.build_email_body(
                account=account,
                summary=summary,
                next_steps=next_steps,
                questions=questions,
                collateral=collateral,
                sources=[f"Chorus {call.chorus_call_id}" if call else "Internal notes"],
            )
        else:
            subject = llm_payload["subject"]
            body = llm_payload["body"]

        row: OutboundMessage = self.messaging.draft_or_send(
            to=to,
            cc=cc,
            subject=subject,
            body=body,
            requested_mode=requested_mode,
            chorus_call_id=(call.chorus_call_id if call else chorus_call_id),
            artifact_id=(artifact.id if artifact else None),
        )

        self.db.add(
            GTMGeneratedAsset(
                account=account,
                module_name="rep.follow_up_draft",
                asset_type="email",
                title=subject,
                content=body,
                metadata_json={"mode": row.mode.value, "to": to, "cc": cc},
                content_hash=sha256_text(body),
                created_by=user,
            )
        )
        self.db.commit()

        payload = {
            "account": account,
            "mode": row.mode.value,
            "subject": subject,
            "body": body,
            "to": to,
            "cc": cc,
            "reason_blocked": row.reason_blocked,
            "citations": self._citations(hits),
        }
        retrieval = self.retriever.retrieval_payload(hits, 8)
        self._record_module_run(
            module_name="rep.follow_up_draft",
            actor=user,
            input_payload={"account": account, "to": to, "cc": cc, "mode": requested_mode, "tone": tone},
            retrieval_payload=retrieval,
            output_payload={k: v for k, v in payload.items() if k != "citations"},
            status=AuditStatus.OK.value,
        )
        return payload, retrieval

    def rep_deal_risk(
        self,
        *,
        user: str,
        account: str,
        chorus_call_id: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        ask = "Assess deal risk and produce mitigation actions."
        call, artifact = self._latest_call(account, chorus_call_id)
        hits = self._collect_hits(account=account, ask=ask, user_email=user, chorus_call_id=chorus_call_id)

        model = self._resolve_model()
        persona_name, persona_prompt = self._resolve_persona("sales_representative")
        llm_payload = self.llm.answer_rep_deal_risk(
            account=account,
            ask=ask,
            hits=hits,
            model=model,
            persona_name=persona_name,
            persona_prompt=persona_prompt,
        )

        if llm_payload is None:
            risks = []
            for raw in (artifact.risks if artifact else [])[:4]:
                risks.append(
                    {
                        "severity": "high",
                        "signal": raw,
                        "impact": "Can delay timeline or reduce confidence in technical/commercial fit.",
                        "mitigation": "Assign owner, due date, and clear exit criteria in next account review.",
                    }
                )
            if not risks:
                risks = [
                    {
                        "severity": "medium",
                        "signal": "Key success criteria are not fully documented.",
                        "impact": "POC may drift without a clear pass/fail gate.",
                        "mitigation": "Publish written success criteria and confirm stakeholder sign-off.",
                    }
                ]
            payload = {
                "account": account,
                "risk_level": "high" if any(r["severity"] == "high" for r in risks) else "medium",
                "risks": risks,
                "action_plan": [
                    "Review top 3 risks with AE/SE and assign owners.",
                    "Set due dates before next customer checkpoint.",
                    "Track risk burn-down weekly until business case close.",
                ],
                "citations": self._citations(hits),
            }
        else:
            payload = {
                "account": account,
                **llm_payload,
                "citations": self._citations(hits),
            }

        for item in payload["risks"]:
            self.db.add(
                GTMRiskSignal(
                    account=account,
                    signal_type="deal_risk",
                    severity=item["severity"],
                    description=item["signal"],
                    owner_email=(call.rep_email if call else user),
                    source_call_id=(call.chorus_call_id if call else chorus_call_id),
                    due_date=(date.today()),
                    metadata_json={"impact": item.get("impact"), "mitigation": item.get("mitigation")},
                )
            )
        self.db.commit()

        retrieval = self.retriever.retrieval_payload(hits, 8)
        self._record_module_run(
            module_name="rep.deal_risk",
            actor=user,
            input_payload={"account": account, "chorus_call_id": chorus_call_id},
            retrieval_payload=retrieval,
            output_payload={k: v for k, v in payload.items() if k != "citations"},
            status=AuditStatus.OK.value,
        )
        return payload, retrieval

    def se_poc_plan(
        self,
        *,
        user: str,
        account: str,
        chorus_call_id: str | None,
        target_offering: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        ask = "Create a practical POC plan and readiness assessment."
        hits = self._collect_hits(account=account, ask=ask, user_email=user, chorus_call_id=chorus_call_id)
        model = self._resolve_model()
        persona_name, persona_prompt = self._resolve_persona("se")
        llm_payload = self.llm.answer_se_poc_plan(
            account=account,
            ask=ask,
            hits=hits,
            target_offering=target_offering,
            model=model,
            persona_name=persona_name,
            persona_prompt=persona_prompt,
        )

        config: KBConfig | None = self.db.get(KBConfig, 1)
        poc_kit_url = (config.se_poc_kit_url if config else None) or None

        if llm_payload is None:
            payload = {
                "account": account,
                "readiness_score": 68,
                "readiness_summary": "Ready to start a scoped technical validation with 2-3 blockers to resolve in week 1.",
                "gaps": [
                    "Top query benchmark set and latency targets are incomplete.",
                    "Data refresh/freshness SLO is not yet confirmed.",
                    "Stakeholder sign-off process needs explicit owner mapping.",
                ],
                "workplan": [
                    "Week 1: baseline workload, ingest profile, and success metrics.",
                    "Week 2: run benchmark + migration rehearsal with production-like patterns.",
                    "Week 3: executive readout with pass/fail recommendation.",
                ],
                "success_criteria": [
                    "Meet agreed p95 latency for critical queries.",
                    "Sustain target write throughput with acceptable replication freshness.",
                    "Complete at least one schema-change scenario during traffic.",
                ],
                "status": "conditional",
                "poc_kit_url": poc_kit_url,
                "citations": self._citations(hits),
            }
        else:
            payload = {
                "account": account,
                **llm_payload,
                "poc_kit_url": poc_kit_url,
                "citations": self._citations(hits),
            }

        self.db.add(
            GTMPOCPlan(
                account=account,
                status=payload["status"],
                readiness_score=payload["readiness_score"],
                readiness_summary=payload["readiness_summary"],
                plan_json={
                    "gaps": payload["gaps"],
                    "workplan": payload["workplan"],
                    "success_criteria": payload["success_criteria"],
                },
                poc_kit_url=poc_kit_url,
                created_by=user,
            )
        )
        self.db.commit()

        retrieval = self.retriever.retrieval_payload(hits, 8)
        self._record_module_run(
            module_name="se.poc_plan",
            actor=user,
            input_payload={"account": account, "chorus_call_id": chorus_call_id, "target_offering": target_offering},
            retrieval_payload=retrieval,
            output_payload={k: v for k, v in payload.items() if k != "citations"},
            status=AuditStatus.OK.value,
        )
        return payload, retrieval

    def se_poc_readiness(
        self,
        *,
        user: str,
        account: str,
        chorus_call_id: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        ask = "Assess POC readiness and required inputs."
        hits = self._collect_hits(account=account, ask=ask, user_email=user, chorus_call_id=chorus_call_id)
        model = self._resolve_model()
        persona_name, persona_prompt = self._resolve_persona("se")
        llm_payload = self.llm.answer_se_poc_readiness(
            account=account,
            ask=ask,
            hits=hits,
            model=model,
            persona_name=persona_name,
            persona_prompt=persona_prompt,
        )

        if llm_payload is None:
            payload = {
                "account": account,
                "readiness_score": 62,
                "readiness_summary": "POC is conditionally ready pending workload and governance inputs.",
                "blockers": [
                    "Missing signed workload acceptance criteria.",
                    "No confirmed owner for production-like data extraction.",
                ],
                "required_inputs": [
                    "Top 10 queries with latency targets",
                    "Daily ingest/write profile",
                    "Security and compliance review owner",
                ],
                "status": "conditional",
                "citations": self._citations(hits),
            }
        else:
            payload = {
                "account": account,
                **llm_payload,
                "citations": self._citations(hits),
            }

        retrieval = self.retriever.retrieval_payload(hits, 8)
        self._record_module_run(
            module_name="se.poc_readiness",
            actor=user,
            input_payload={"account": account, "chorus_call_id": chorus_call_id},
            retrieval_payload=retrieval,
            output_payload={k: v for k, v in payload.items() if k != "citations"},
            status=AuditStatus.OK.value,
        )
        return payload, retrieval

    def se_architecture_fit(
        self,
        *,
        user: str,
        account: str,
        chorus_call_id: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        ask = "Evaluate architecture fit and migration path for this account."
        hits = self._collect_hits(account=account, ask=ask, user_email=user, chorus_call_id=chorus_call_id)
        model = self._resolve_model()
        persona_name, persona_prompt = self._resolve_persona("se")
        llm_payload = self.llm.answer_se_architecture_fit(
            account=account,
            ask=ask,
            hits=hits,
            model=model,
            persona_name=persona_name,
            persona_prompt=persona_prompt,
        )

        if llm_payload is None:
            payload = {
                "account": account,
                "fit_summary": "Strong fit when OLTP + real-time analytics coexist and MySQL compatibility is mandatory.",
                "strong_fit_for": [
                    "High-concurrency transactional workloads with growth pressure",
                    "Mixed OLTP + analytical read patterns requiring near-real-time freshness",
                    "Teams seeking scale-out without manual sharding",
                ],
                "watchouts": [
                    "Unclear SLOs for TiFlash freshness and long-running analytical scans",
                    "Schema-change expectations must be validated under production-like load",
                ],
                "migration_path": [
                    "Baseline current MySQL/Aurora schema and top query workloads",
                    "Run CDC + dual-read validation on a scoped domain",
                    "Cut over by service boundary with rollback checkpoints",
                ],
                "citations": self._citations(hits),
            }
        else:
            payload = {
                "account": account,
                **llm_payload,
                "citations": self._citations(hits),
            }

        retrieval = self.retriever.retrieval_payload(hits, 8)
        self._record_module_run(
            module_name="se.architecture_fit",
            actor=user,
            input_payload={"account": account, "chorus_call_id": chorus_call_id},
            retrieval_payload=retrieval,
            output_payload={k: v for k, v in payload.items() if k != "citations"},
            status=AuditStatus.OK.value,
        )
        return payload, retrieval

    def se_competitor_coach(
        self,
        *,
        user: str,
        account: str,
        chorus_call_id: str | None,
        competitor: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        call, artifact = self._latest_call(account, chorus_call_id)
        resolved_competitor = (competitor or "").strip() or (
            artifact.competitors_mentioned[0] if artifact and artifact.competitors_mentioned else "Incumbent"
        )
        ask = f"Build a competitor coaching brief versus {resolved_competitor}."
        hits = self._collect_hits(account=account, ask=ask, user_email=user, chorus_call_id=chorus_call_id)
        model = self._resolve_model()
        persona_name, persona_prompt = self._resolve_persona("se")
        llm_payload = self.llm.answer_se_competitor_coach(
            account=account,
            ask=ask,
            competitor=resolved_competitor,
            hits=hits,
            model=model,
            persona_name=persona_name,
            persona_prompt=persona_prompt,
        )

        if llm_payload is None:
            payload = {
                "account": account,
                "competitor": resolved_competitor,
                "positioning": [
                    "Lead with operational simplicity and MySQL ecosystem compatibility.",
                    "Anchor on single-platform HTAP story with concrete workload metrics.",
                ],
                "proof_points": [
                    "Show query latency + ingest throughput evidence from scoped benchmark.",
                    "Demonstrate online schema change behavior under active traffic.",
                ],
                "landmines": [
                    "Avoid generic performance claims without matched workload context.",
                    "Do not skip migration-risk discussion for app/query compatibility.",
                ],
                "discovery_questions": [
                    "Which competitor proof points are most trusted by the buying committee?",
                    "What workload in your environment is hardest for the incumbent today?",
                    "What would make a migration operationally unacceptable?",
                ],
                "citations": self._citations(hits),
            }
        else:
            payload = {
                "account": account,
                **llm_payload,
                "citations": self._citations(hits),
            }

        retrieval = self.retriever.retrieval_payload(hits, 8)
        self._record_module_run(
            module_name="se.competitor_coach",
            actor=user,
            input_payload={
                "account": account,
                "chorus_call_id": chorus_call_id,
                "competitor": resolved_competitor,
            },
            retrieval_payload=retrieval,
            output_payload={k: v for k, v in payload.items() if k != "citations"},
            status=AuditStatus.OK.value,
        )
        return payload, retrieval

    def marketing_intelligence(
        self,
        *,
        user: str,
        regions: list[str],
        verticals: list[str],
        lookback_days: int,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        ask = (
            f"Summarize market signals and campaign priorities for regions {regions} and verticals {verticals} "
            f"over the last {lookback_days} days."
        )
        query = " ".join(["TiDB GTM signals", *regions, *verticals]).strip()
        hits = self.retriever.search(
            query,
            top_k=10,
            filters={
                "source_type": [SourceType.GOOGLE_DRIVE.value, SourceType.FEISHU.value, SourceType.CHORUS.value],
                "viewer_email": (user or "").strip().lower(),
            },
        )

        model = self._resolve_model()
        persona_name, persona_prompt = self._resolve_persona("marketing_specialist")
        llm_payload = self.llm.answer_marketing_intelligence(
            ask=ask,
            regions=regions,
            verticals=verticals,
            hits=hits,
            model=model,
            persona_name=persona_name,
            persona_prompt=persona_prompt,
        )

        if llm_payload is None:
            payload = {
                "summary": "Signal review suggests prioritizing proof-driven vertical campaigns tied to active technical evaluations.",
                "top_signals": [
                    "Performance + migration-risk objections dominate early technical calls.",
                    "Healthcare and financial services opportunities request compliance + operational proof.",
                    "POC conversion rises when benchmark + architecture assets are bundled.",
                ],
                "campaign_angles": [
                    "HTAP without re-platforming app teams",
                    "MySQL compatibility with scale-out operations",
                    "Cost-to-value narrative anchored to consolidation outcomes",
                ],
                "priority_accounts": [
                    "Evernorth Health",
                    "Northwind Health",
                    "Summit Retail",
                ],
                "next_actions": [
                    "Launch two vertical-tailored nurture sequences with technical proof assets.",
                    "Coordinate weekly AE/SE marketing review on top 10 active accounts.",
                    "Track campaign-assisted stage progression against baseline.",
                ],
            }
        else:
            payload = llm_payload

        self.db.add(
            GTMTrendInsight(
                region=", ".join(regions) or "All",
                vertical=", ".join(verticals) or "All",
                summary=payload["summary"],
                top_signals=payload["top_signals"],
                recommended_plays=payload["next_actions"],
                created_by=user,
            )
        )
        self.db.commit()

        retrieval = self.retriever.retrieval_payload(hits, 10)
        self._record_module_run(
            module_name="marketing.intelligence",
            actor=user,
            input_payload={"regions": regions, "verticals": verticals, "lookback_days": lookback_days},
            retrieval_payload=retrieval,
            output_payload=payload,
            status=AuditStatus.OK.value,
        )
        return payload, retrieval
