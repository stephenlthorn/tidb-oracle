from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class KBConfigUpdate(BaseModel):
    google_drive_enabled: bool | None = None
    google_drive_folder_ids: str | None = None
    feishu_enabled: bool | None = None
    feishu_folder_token: str | None = None
    feishu_app_id: str | None = None
    feishu_app_secret: str | None = None
    chorus_enabled: bool | None = None
    retrieval_top_k: int | None = Field(default=None, ge=1, le=50)
    llm_model: str | None = None
    web_search_enabled: bool | None = None
    code_interpreter_enabled: bool | None = None


class KBConfigRead(BaseModel):
    google_drive_enabled: bool
    google_drive_folder_ids: str | None
    feishu_enabled: bool
    feishu_folder_token: str | None
    feishu_app_id: str | None
    # Note: feishu_app_secret intentionally omitted from read schema (write-only)
    chorus_enabled: bool
    retrieval_top_k: int
    llm_model: str
    web_search_enabled: bool
    code_interpreter_enabled: bool
    updated_at: datetime

    model_config = {"from_attributes": True}
