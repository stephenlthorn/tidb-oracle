from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "TiDB Oracle API"
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    auto_create_schema: bool = True
    cors_allow_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/tidb_oracle"
    redis_url: str = "redis://localhost:6379/0"

    embedding_dimensions: int = 1536
    retrieval_top_k: int = 8

    openai_base_url: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1"
    openai_embedding_model: str = "text-embedding-3-small"
    enterprise_mode: bool = False
    security_require_private_llm_endpoint: bool = False
    security_allowed_llm_base_urls: str = ""
    security_fail_closed_on_missing_llm_key: bool = False
    security_fail_closed_on_missing_embedding_key: bool = False
    security_redact_before_llm: bool = True
    security_redact_audit_logs: bool = False
    security_trusted_host_allowlist: str = ""
    security_allow_insecure_http_llm: bool = False

    google_drive_client_id: str | None = None
    google_drive_client_secret: str | None = None
    google_drive_service_account_json: str | None = None
    google_drive_oauth_token_path: str = ".google-drive-token.json"
    google_drive_root_folder_id: str | None = None
    fake_drive_include_github: bool = False
    google_drive_folder_ids: str = ""

    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_base_url: str = "https://open.feishu.cn/open-apis"

    chorus_api_key: str | None = None
    chorus_base_url: str | None = None

    email_mode: str = "draft"
    internal_domain_allowlist: str = "pingcap.com"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "tidb-oracle@pingcap.com"

    slack_bot_token: str | None = None
    slack_default_channel: str | None = None

    @property
    def drive_folder_ids(self) -> List[str]:
        return [fid.strip() for fid in self.google_drive_folder_ids.split(",") if fid.strip()]

    @property
    def domain_allowlist(self) -> List[str]:
        return [d.strip().lower() for d in self.internal_domain_allowlist.split(",") if d.strip()]

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @property
    def trusted_hosts(self) -> List[str]:
        return [h.strip() for h in self.security_trusted_host_allowlist.split(",") if h.strip()]

    @staticmethod
    def normalize_base_url(value: str) -> str:
        parsed = urlparse(value.strip())
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid base URL: {value}")
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"

    @property
    def allowed_llm_base_urls(self) -> List[str]:
        values = [v.strip() for v in self.security_allowed_llm_base_urls.split(",") if v.strip()]
        normalized: list[str] = []
        for value in values:
            normalized.append(self.normalize_base_url(value))
        return normalized

    def is_allowed_llm_base_url(self, value: str | None) -> bool:
        if not value:
            return False
        allowed = self.allowed_llm_base_urls
        if not allowed:
            return True
        return self.normalize_base_url(value) in set(allowed)


@lru_cache
def get_settings() -> Settings:
    return Settings()
