from __future__ import annotations

from pydantic import BaseModel, Field


class MarketResearchRequest(BaseModel):
    user: str = "oracle@pingcap.com"
    regions: list[str] = Field(default_factory=lambda: ["East", "Central"])
    strategic_goal: str = Field(
        default="Build an execution-ready strategic account list for East and Central territories."
    )
    current_customers_csv: str = ""
    pipeline_csv: str = ""
    additional_context: str | None = None
    top_n: int = Field(default=8, ge=1, le=20)
    openai_token: str | None = None


class StrategicAccountItem(BaseModel):
    account: str
    motion_type: str
    region: str
    priority: str
    why_now: str
    actions: list[str]
    suggested_assets: list[str]


class MarketResearchResponse(BaseModel):
    summary: str
    required_inputs: list[str]
    priority_accounts: list[StrategicAccountItem]
    execution_plan: list[str]
