from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


Mode = Literal["oracle", "call_assistant"]


class ChatFilters(BaseModel):
    source_type: list[str] = Field(default_factory=list)
    account: list[str] = Field(default_factory=list)


class ChatContext(BaseModel):
    chorus_call_id: str | None = None


class ChatRequest(BaseModel):
    mode: Mode = "oracle"
    user: str
    message: str
    top_k: int = 8
    filters: ChatFilters = Field(default_factory=ChatFilters)
    context: ChatContext = Field(default_factory=ChatContext)
    openai_token: str | None = None


class Citation(BaseModel):
    title: str
    source_type: str
    source_id: str
    chunk_id: UUID
    quote: str | None = None
    relevance: float
    file_id: str | None = None
    timestamp: str | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    follow_up_questions: list[str]


class CallAssistantResponse(BaseModel):
    what_happened: list[str]
    risks: list[str]
    next_steps: list[str]
    questions_to_ask_next_call: list[str]
    citations: list[Citation]


class ChatEnvelope(BaseModel):
    mode: Mode
    data: dict[str, Any]
