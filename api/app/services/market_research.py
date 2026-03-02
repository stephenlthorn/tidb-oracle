from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models import KBConfig
from app.schemas.market_research import MarketResearchRequest
from app.services.llm import LLMService


CUSTOMER_REQUIRED_FIELDS = ("account", "region", "industry", "current_platform", "use_case", "arr")
PIPELINE_REQUIRED_FIELDS = (
    "account",
    "region",
    "stage",
    "industry",
    "workload",
    "est_arr",
    "close_quarter",
    "competing_vendor",
)


def _normalize_key(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    return cleaned.strip("_")


def _parse_arr_value(value: str | None) -> float:
    if not value:
        return 0.0
    digits = re.sub(r"[^0-9.]", "", value)
    if not digits:
        return 0.0
    try:
        raw = float(digits)
    except ValueError:
        return 0.0
    lowered = value.lower()
    if "m" in lowered:
        return raw * 1_000_000
    if "k" in lowered:
        return raw * 1_000
    return raw


@dataclass
class ParsedCsv:
    rows: list[dict[str, str]]
    missing_required_fields: list[str]


def parse_csv_rows(raw_csv: str, required_fields: tuple[str, ...]) -> ParsedCsv:
    payload = (raw_csv or "").strip()
    if not payload:
        return ParsedCsv(rows=[], missing_required_fields=list(required_fields))

    reader = csv.DictReader(io.StringIO(payload))
    if not reader.fieldnames:
        return ParsedCsv(rows=[], missing_required_fields=list(required_fields))

    normalized_headers = [_normalize_key(header) for header in reader.fieldnames]
    missing_fields = [field for field in required_fields if field not in normalized_headers]

    rows: list[dict[str, str]] = []
    for raw_row in reader:
        normalized_row: dict[str, str] = {}
        has_value = False
        for original_key, value in raw_row.items():
            if original_key is None:
                continue
            key = _normalize_key(original_key)
            cleaned_value = (value or "").strip()
            normalized_row[key] = cleaned_value
            if cleaned_value:
                has_value = True
        if has_value:
            rows.append(normalized_row)
    return ParsedCsv(rows=rows, missing_required_fields=missing_fields)


class MarketResearchService:
    def __init__(self, db: Session, openai_token: str | None = None) -> None:
        self.db = db
        self.llm = LLMService(api_key=openai_token)

    @staticmethod
    def required_inputs_list() -> list[str]:
        return [
            "Current customers CSV with headers: account, region, industry, current_platform, use_case, arr",
            "Pipeline CSV with headers: account, region, stage, industry, workload, est_arr, close_quarter, competing_vendor",
            "Primary GTM goal for the next 30-90 days",
            "Territory focus (East/Central defaults can be changed)",
            "Optional context: rep capacity, must-win accounts, executive priorities",
        ]

    @staticmethod
    def _normalize_region(region: str, fallback: str = "Unknown") -> str:
        value = (region or "").strip()
        return value if value else fallback

    def _build_fallback_plan(
        self,
        *,
        regions: list[str],
        customers: list[dict[str, str]],
        pipeline: list[dict[str, str]],
        strategic_goal: str,
        top_n: int,
        required_inputs: list[str],
    ) -> dict[str, Any]:
        region_set = {region.strip().lower() for region in regions if region.strip()}
        candidates: list[dict[str, Any]] = []

        for row in customers:
            region = self._normalize_region(row.get("region", ""))
            if region_set and region.lower() not in region_set:
                continue
            arr = _parse_arr_value(row.get("arr"))
            score = 45 + min(25, arr / 80_000)
            candidates.append(
                {
                    "account": row.get("account") or "Unknown Account",
                    "motion_type": "customer",
                    "region": region,
                    "stage": "existing",
                    "arr": arr,
                    "score": score,
                    "industry": row.get("industry", ""),
                    "platform": row.get("current_platform", ""),
                    "workload": row.get("use_case", ""),
                }
            )

        stage_boost = {
            "business case": 30,
            "poc": 25,
            "technical validation": 20,
            "evaluation": 16,
            "discovery": 10,
        }
        for row in pipeline:
            region = self._normalize_region(row.get("region", ""))
            if region_set and region.lower() not in region_set:
                continue
            arr = _parse_arr_value(row.get("est_arr"))
            stage = (row.get("stage") or "").strip().lower()
            boost = max((value for key, value in stage_boost.items() if key in stage), default=8)
            score = 35 + boost + min(30, arr / 70_000)
            candidates.append(
                {
                    "account": row.get("account") or "Unknown Account",
                    "motion_type": "pipeline",
                    "region": region,
                    "stage": row.get("stage") or "unknown",
                    "arr": arr,
                    "score": score,
                    "industry": row.get("industry", ""),
                    "platform": row.get("competing_vendor", ""),
                    "workload": row.get("workload", ""),
                }
            )

        ranked = sorted(candidates, key=lambda item: item["score"], reverse=True)[:top_n]
        priority_accounts: list[dict[str, Any]] = []
        for item in ranked:
            priority = "High" if item["score"] >= 65 else "Medium"
            stage_text = item["stage"] if item["stage"] else "current motion"
            why_now = (
                f"{item['motion_type'].title()} account in {item['region']} with {stage_text} momentum "
                f"and estimated value ${item['arr']:,.0f}."
            )
            actions = [
                "Confirm executive sponsor and next meeting date.",
                "Align technical success criteria and commercial decision criteria.",
                "Prepare one account-specific follow-up email with clear owner and due date.",
            ]
            if item["motion_type"] == "pipeline":
                actions[0] = "Lock next milestone exit criteria and stakeholder map."
            assets = [
                "TiDB vs incumbent comparison one-pager",
                "Relevant customer story by industry",
                "POC or migration checklist tailored to workload",
            ]
            priority_accounts.append(
                {
                    "account": item["account"],
                    "motion_type": item["motion_type"],
                    "region": item["region"],
                    "priority": priority,
                    "why_now": why_now,
                    "actions": actions,
                    "suggested_assets": assets,
                }
            )

        if not priority_accounts:
            summary = (
                "No strategic accounts could be ranked yet because parsed territory data is empty. "
                "Paste both CSV inputs and retry."
            )
        else:
            summary = (
                f"Generated a territory strategy for {len(priority_accounts)} prioritized accounts "
                f"across {', '.join(regions) if regions else 'selected regions'} aligned to: {strategic_goal}"
            )

        execution_plan = [
            "Week 1: Validate account data quality and confirm top 5 must-win accounts with leadership.",
            "Week 2: Run account-by-account action reviews with AE + SE owners.",
            "Week 3-4: Track progression, blockers, and asset usage; rebalance territory focus weekly.",
        ]

        return {
            "summary": summary,
            "required_inputs": required_inputs,
            "priority_accounts": priority_accounts,
            "execution_plan": execution_plan,
        }

    def generate(self, req: MarketResearchRequest) -> tuple[dict[str, Any], dict[str, Any]]:
        customers = parse_csv_rows(req.current_customers_csv, CUSTOMER_REQUIRED_FIELDS)
        pipeline = parse_csv_rows(req.pipeline_csv, PIPELINE_REQUIRED_FIELDS)
        required_inputs = self.required_inputs_list()
        if customers.missing_required_fields:
            required_inputs.append(
                "Customer CSV is missing headers: " + ", ".join(customers.missing_required_fields)
            )
        if pipeline.missing_required_fields:
            required_inputs.append(
                "Pipeline CSV is missing headers: " + ", ".join(pipeline.missing_required_fields)
            )
        if not customers.rows:
            required_inputs.append("Provide at least 3 current customer rows to calibrate expansion/retention priorities.")
        if not pipeline.rows:
            required_inputs.append("Provide at least 5 active pipeline rows to rank new-logo opportunities.")

        parse_meta = {
            "regions": req.regions,
            "customer_rows": len(customers.rows),
            "pipeline_rows": len(pipeline.rows),
            "customer_missing_fields": customers.missing_required_fields,
            "pipeline_missing_fields": pipeline.missing_required_fields,
        }

        config: KBConfig | None = self.db.get(KBConfig, 1)
        model = config.llm_model if config else None
        persona_prompt = (config.persona_prompt if config else "") or ""

        llm_payload = self.llm.answer_market_research(
            strategic_goal=req.strategic_goal,
            regions=req.regions,
            current_customers=customers.rows,
            pipeline=pipeline.rows,
            additional_context=req.additional_context or "",
            top_n=req.top_n,
            model=model,
            persona_name="sales_representative",
            persona_prompt=persona_prompt,
            required_inputs=required_inputs,
        )
        if llm_payload is not None:
            return llm_payload, parse_meta

        fallback = self._build_fallback_plan(
            regions=req.regions,
            customers=customers.rows,
            pipeline=pipeline.rows,
            strategic_goal=req.strategic_goal,
            top_n=req.top_n,
            required_inputs=required_inputs,
        )
        return fallback, parse_meta
