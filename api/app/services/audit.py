from __future__ import annotations

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models import AuditLog, AuditStatus
from app.utils.redaction import redact_payload


def write_audit_log(
    db: Session,
    *,
    actor: str,
    action: str,
    input_payload: dict,
    retrieval_payload: dict | None = None,
    output_payload: dict | None = None,
    status: AuditStatus = AuditStatus.OK,
    error_message: str | None = None,
) -> AuditLog:
    settings = get_settings()
    safe_input = input_payload
    safe_retrieval = retrieval_payload or {}
    safe_output = output_payload or {}
    safe_error = error_message
    if settings.security_redact_audit_logs:
        safe_input = redact_payload(safe_input)
        safe_retrieval = redact_payload(safe_retrieval)
        safe_output = redact_payload(safe_output)
        safe_error = redact_payload(safe_error) if safe_error else None

    row = AuditLog(
        actor=actor,
        action=action,
        input_json=jsonable_encoder(safe_input),
        retrieval_json=jsonable_encoder(safe_retrieval),
        output_json=jsonable_encoder(safe_output),
        status=status,
        error_message=safe_error,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
