from __future__ import annotations

from pydantic import BaseModel, Field


class DraftMessageRequest(BaseModel):
    chorus_call_id: str
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    mode: str = "draft"
    tone: str = "crisp"
    include: list[str] = Field(default_factory=lambda: ["recommended_next_steps", "questions", "collateral"])


class RegenerateDraftRequest(BaseModel):
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    mode: str = "draft"


class DraftMessageResponse(BaseModel):
    mode: str
    channel: str = "email"
    to: list[str]
    cc: list[str]
    subject: str
    body: str
    reason_blocked: str | None = None
