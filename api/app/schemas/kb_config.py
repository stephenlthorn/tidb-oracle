from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class KBConfigUpdate(BaseModel):
    google_drive_enabled: bool | None = None
    google_drive_folder_ids: str | None = None
    feishu_enabled: bool | None = None
    feishu_root_tokens: str | None = None
    feishu_oauth_enabled: bool | None = None
    feishu_folder_token: str | None = None
    feishu_app_id: str | None = None
    feishu_app_secret: str | None = None
    chorus_enabled: bool | None = None
    retrieval_top_k: int | None = Field(default=None, ge=1, le=50)
    llm_model: str | None = None
    web_search_enabled: bool | None = None
    code_interpreter_enabled: bool | None = None
    persona_name: str | None = None
    persona_prompt: str | None = None
    se_poc_kit_url: str | None = None
    feature_flags_json: dict | None = None


class KBConfigRead(BaseModel):
    google_drive_enabled: bool
    google_drive_folder_ids: str | None
    feishu_enabled: bool
    feishu_root_tokens: str | None
    feishu_oauth_enabled: bool
    feishu_folder_token: str | None
    feishu_app_id: str | None
    # Note: feishu_app_secret intentionally omitted from read schema (write-only)
    chorus_enabled: bool
    retrieval_top_k: int
    llm_model: str
    web_search_enabled: bool
    code_interpreter_enabled: bool
    persona_name: str
    persona_prompt: str | None
    se_poc_kit_url: str | None
    feature_flags_json: dict
    updated_at: datetime

    model_config = {"from_attributes": True}
