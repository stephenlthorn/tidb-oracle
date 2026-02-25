from __future__ import annotations

from datetime import date

from dateutil.parser import isoparse
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import db_session
from app.core.settings import get_settings
from app.ingest.drive_ingestor import DriveIngestor
from app.ingest.feishu_ingestor import FeishuIngestor
from app.ingest.transcript_ingestor import TranscriptIngestor
from app.models import AuditLog, AuditStatus, KBConfig
from app.schemas.kb_config import KBConfigRead, KBConfigUpdate
from app.services.audit import write_audit_log

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/security/settings")
def security_settings() -> dict:
    settings = get_settings()
    return {
        "enterprise_mode": settings.enterprise_mode,
        "security_require_private_llm_endpoint": settings.security_require_private_llm_endpoint,
        "security_allowed_llm_base_urls": settings.allowed_llm_base_urls,
        "llm_base_url_configured": bool(settings.openai_base_url),
        "llm_base_url_allowed": settings.is_allowed_llm_base_url(settings.openai_base_url)
        if settings.openai_base_url
        else None,
        "security_fail_closed_on_missing_llm_key": settings.security_fail_closed_on_missing_llm_key,
        "security_fail_closed_on_missing_embedding_key": settings.security_fail_closed_on_missing_embedding_key,
        "security_redact_before_llm": settings.security_redact_before_llm,
        "security_redact_audit_logs": settings.security_redact_audit_logs,
        "security_trusted_host_allowlist": settings.trusted_hosts,
        "internal_domain_allowlist": settings.domain_allowlist,
        "email_mode": settings.email_mode,
        "smtp_tls_configured": bool(settings.smtp_username and settings.smtp_password),
    }


@router.post("/sync/drive")
def sync_drive(
    since: str | None = Query(default=None, description="ISO timestamp"),
    db: Session = Depends(db_session),
) -> dict:
    since_dt = isoparse(since) if since else None
    ingestor = DriveIngestor(db)
    result = ingestor.sync(since=since_dt)
    write_audit_log(
        db,
        actor="system",
        action="sync_drive",
        input_payload={"since": since},
        retrieval_payload={},
        output_payload=result,
        status=AuditStatus.OK,
    )
    return result


@router.post("/sync/chorus")
def sync_chorus(
    since: str | None = Query(default=None, description="YYYY-MM-DD"),
    db: Session = Depends(db_session),
) -> dict:
    since_date = date.fromisoformat(since) if since else None
    ingestor = TranscriptIngestor(db)
    result = ingestor.sync(since=since_date)
    write_audit_log(
        db,
        actor="system",
        action="sync_chorus",
        input_payload={"since": since},
        retrieval_payload={},
        output_payload=result,
        status=AuditStatus.OK,
    )
    return result


@router.get("/audit")
def audit(limit: int = Query(default=100, ge=1, le=2000), db: Session = Depends(db_session)) -> list[dict]:
    rows = db.execute(select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)).scalars().all()
    return [
        {
            "id": str(row.id),
            "timestamp": row.timestamp,
            "actor": row.actor,
            "action": row.action,
            "status": row.status.value,
            "input": row.input_json,
            "retrieval": row.retrieval_json,
            "output": row.output_json,
            "error_message": row.error_message,
        }
        for row in rows
    ]


@router.get("/kb-config", response_model=KBConfigRead)
def get_kb_config(db: Session = Depends(db_session)):
    config = db.get(KBConfig, 1)
    if config is None:
        config = KBConfig(id=1)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


@router.put("/kb-config", response_model=KBConfigRead)
def update_kb_config(update: KBConfigUpdate, db: Session = Depends(db_session)):
    config = db.get(KBConfig, 1)
    if config is None:
        config = KBConfig(id=1)
    for field, value in update.model_dump(exclude_none=True).items():
        setattr(config, field, value)
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@router.post("/sync/feishu")
def sync_feishu(db: Session = Depends(db_session)) -> dict:
    settings = get_settings()
    kb_config: KBConfig | None = db.get(KBConfig, 1)

    folder_token = (kb_config.feishu_folder_token if kb_config else None) or None
    app_id = (kb_config.feishu_app_id if kb_config else None) or settings.feishu_app_id
    app_secret = (kb_config.feishu_app_secret if kb_config else None) or settings.feishu_app_secret

    if not folder_token:
        return {"status": "error", "message": "No Feishu folder token configured. Set it in the KB Config panel."}
    if not app_id or not app_secret:
        return {"status": "error", "message": "Feishu app_id / app_secret not configured."}

    ingestor = FeishuIngestor(db)
    result = ingestor.sync_folder(folder_token)
    write_audit_log(
        db,
        actor="system",
        action="sync_feishu",
        input_payload={"folder_token": folder_token},
        retrieval_payload={},
        output_payload=result,
        status=AuditStatus.OK,
    )
    return {"status": "ok", **result}
