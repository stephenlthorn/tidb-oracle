from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.chat import Citation


MessageMode = Literal["draft", "send"]


class RepAccountBriefRequest(BaseModel):
    user: str = "oracle@pingcap.com"
    account: str
    chorus_call_id: str | None = None


class RepAccountBriefResponse(BaseModel):
    account: str
    summary: str
    business_context: list[str]
    decision_criteria: list[str]
    recommended_assets: list[str]
    next_meeting_agenda: list[str]
    citations: list[Citation] = Field(default_factory=list)


class RepDiscoveryQuestionsRequest(BaseModel):
    user: str = "oracle@pingcap.com"
    account: str
    chorus_call_id: str | None = None
    count: int = Field(default=6, ge=3, le=12)


class RepDiscoveryQuestionsResponse(BaseModel):
    account: str
    questions: list[str]
    intent: list[str]
    citations: list[Citation] = Field(default_factory=list)


class RepFollowUpDraftRequest(BaseModel):
    user: str = "oracle@pingcap.com"
    account: str
    chorus_call_id: str | None = None
    mode: MessageMode = "draft"
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    tone: str = "crisp"


class RepFollowUpDraftResponse(BaseModel):
    account: str
    mode: str
    subject: str
    body: str
    to: list[str]
    cc: list[str]
    reason_blocked: str | None = None
    citations: list[Citation] = Field(default_factory=list)


class RiskItem(BaseModel):
    severity: str
    signal: str
    impact: str
    mitigation: str


class RepDealRiskRequest(BaseModel):
    user: str = "oracle@pingcap.com"
    account: str
    chorus_call_id: str | None = None


class RepDealRiskResponse(BaseModel):
    account: str
    risk_level: str
    risks: list[RiskItem]
    action_plan: list[str]
    citations: list[Citation] = Field(default_factory=list)


class SEPocPlanRequest(BaseModel):
    user: str = "oracle@pingcap.com"
    account: str
    chorus_call_id: str | None = None
    target_offering: str = "TiDB Cloud Dedicated"


class SEPocPlanResponse(BaseModel):
    account: str
    readiness_score: int = Field(ge=0, le=100)
    readiness_summary: str
    gaps: list[str]
    workplan: list[str]
    success_criteria: list[str]
    status: str
    poc_kit_url: str | None = None
    citations: list[Citation] = Field(default_factory=list)


class SEPocReadinessRequest(BaseModel):
    user: str = "oracle@pingcap.com"
    account: str
    chorus_call_id: str | None = None


class SEPocReadinessResponse(BaseModel):
    account: str
    readiness_score: int = Field(ge=0, le=100)
    readiness_summary: str
    blockers: list[str]
    required_inputs: list[str]
    status: str
    citations: list[Citation] = Field(default_factory=list)


class SEArchitectureFitRequest(BaseModel):
    user: str = "oracle@pingcap.com"
    account: str
    chorus_call_id: str | None = None


class SEArchitectureFitResponse(BaseModel):
    account: str
    fit_summary: str
    strong_fit_for: list[str]
    watchouts: list[str]
    migration_path: list[str]
    citations: list[Citation] = Field(default_factory=list)


class SECompetitorCoachRequest(BaseModel):
    user: str = "oracle@pingcap.com"
    account: str
    chorus_call_id: str | None = None
    competitor: str | None = None


class SECompetitorCoachResponse(BaseModel):
    account: str
    competitor: str
    positioning: list[str]
    proof_points: list[str]
    landmines: list[str]
    discovery_questions: list[str]
    citations: list[Citation] = Field(default_factory=list)


class MarketingIntelligenceRequest(BaseModel):
    user: str = "oracle@pingcap.com"
    regions: list[str] = Field(default_factory=lambda: ["East", "Central"])
    verticals: list[str] = Field(default_factory=list)
    lookback_days: int = Field(default=60, ge=14, le=365)


class MarketingIntelligenceResponse(BaseModel):
    summary: str
    top_signals: list[str]
    campaign_angles: list[str]
    priority_accounts: list[str]
    next_actions: list[str]


class AssetPackItem(BaseModel):
    asset_type: str
    title: str
    owner: str
    purpose: str


class RepFullSolutionRequest(BaseModel):
    user: str = "oracle@pingcap.com"
    account: str
    chorus_call_id: str | None = None
    count: int = Field(default=6, ge=3, le=12)
    mode: MessageMode = "draft"
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    tone: str = "crisp"


class RepFullSolutionResponse(BaseModel):
    account: str
    phase_1_modules: list[str]
    account_brief: RepAccountBriefResponse
    discovery_questions: RepDiscoveryQuestionsResponse
    deal_risk: RepDealRiskResponse
    follow_up_draft: RepFollowUpDraftResponse
    phase_2_execution_focus: list[str]
    phase_2_weekly_cadence: list[str]
    phase_3_assets: list[AssetPackItem]
    phase_3_automation_next_steps: list[str]
    citations: list[Citation] = Field(default_factory=list)


class SEFullSolutionRequest(BaseModel):
    user: str = "oracle@pingcap.com"
    account: str
    chorus_call_id: str | None = None
    target_offering: str = "TiDB Cloud Dedicated"
    competitor: str | None = None


class SEFullSolutionResponse(BaseModel):
    account: str
    phase_1_modules: list[str]
    poc_plan: SEPocPlanResponse
    poc_readiness: SEPocReadinessResponse
    architecture_fit: SEArchitectureFitResponse
    competitor_coach: SECompetitorCoachResponse
    phase_2_validation_matrix: list[dict[str, str]]
    phase_2_red_flags: list[str]
    phase_3_assets: list[AssetPackItem]
    phase_3_handoff_notes: list[str]
    citations: list[Citation] = Field(default_factory=list)


class MarketingFullSolutionRequest(BaseModel):
    user: str = "oracle@pingcap.com"
    regions: list[str] = Field(default_factory=lambda: ["East", "Central"])
    verticals: list[str] = Field(default_factory=list)
    lookback_days: int = Field(default=60, ge=14, le=365)
    campaign_goal: str = "Increase qualified pipeline and improve conversion through technical-proof-led campaigns."


class MarketingFullSolutionResponse(BaseModel):
    phase_1_modules: list[str]
    intelligence: MarketingIntelligenceResponse
    phase_2_campaign_plan: list[str]
    phase_2_targeting_matrix: list[dict[str, str]]
    phase_3_assets: list[AssetPackItem]
    phase_3_measurement_plan: list[str]
    citations: list[Citation] = Field(default_factory=list)
