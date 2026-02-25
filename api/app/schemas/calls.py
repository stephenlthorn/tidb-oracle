from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel


class ChorusCallOut(BaseModel):
    id: UUID
    chorus_call_id: str
    date: date
    account: str
    opportunity: str | None
    stage: str | None
    rep_email: str
    se_email: str | None


class CallArtifactOut(BaseModel):
    id: UUID
    chorus_call_id: str
    summary: str
    objections: list[str]
    competitors_mentioned: list[str]
    risks: list[str]
    next_steps: list[str]
    recommended_collateral: list[dict]
    follow_up_questions: list[str]
