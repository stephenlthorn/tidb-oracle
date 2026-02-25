from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import db_session
from app.models import AuditStatus
from app.schemas.chat import ChatRequest
from app.services.audit import write_audit_log
from app.services.chat_orchestrator import ChatOrchestrator

router = APIRouter()


@router.post("")
def chat(req: ChatRequest, request: Request, db: Session = Depends(db_session)) -> dict:
    openai_token = request.headers.get("X-OpenAI-Token") or req.openai_token
    orchestrator = ChatOrchestrator(db, openai_token=openai_token)

    try:
        data, retrieval = orchestrator.run(
            mode=req.mode,
            user=req.user,
            message=req.message,
            top_k=req.top_k,
            filters=req.filters.model_dump(),
            context=req.context.model_dump(),
        )
        write_audit_log(
            db,
            actor=req.user,
            action="chat",
            input_payload=req.model_dump(),
            retrieval_payload=retrieval,
            output_payload=data,
            status=AuditStatus.OK,
        )
        return data
    except Exception as exc:
        db.rollback()
        write_audit_log(
            db,
            actor=req.user,
            action="chat",
            input_payload=req.model_dump(),
            retrieval_payload={},
            output_payload={},
            status=AuditStatus.ERROR,
            error_message=str(exc),
        )
        raise
