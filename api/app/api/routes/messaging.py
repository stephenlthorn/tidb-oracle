from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import db_session
from app.models import AuditStatus, CallArtifact, ChorusCall
from app.schemas.messaging import DraftMessageRequest
from app.services.audit import write_audit_log
from app.services.messaging import MessagingService

router = APIRouter()


@router.post("/draft")
def draft_message(req: DraftMessageRequest, db: Session = Depends(db_session)) -> dict:
    call = db.execute(select(ChorusCall).where(ChorusCall.chorus_call_id == req.chorus_call_id)).scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="call not found")

    artifact = db.execute(
        select(CallArtifact).where(CallArtifact.chorus_call_id == req.chorus_call_id).order_by(CallArtifact.created_at.desc())
    ).scalars().first()

    if not artifact:
        raise HTTPException(status_code=404, detail="call artifact not found")

    svc = MessagingService(db)
    subject = svc.build_email_subject(call.account)
    body = svc.build_email_body(
        account=call.account,
        summary=artifact.summary,
        next_steps=artifact.next_steps,
        questions=artifact.follow_up_questions,
        collateral=artifact.recommended_collateral,
        sources=[f"Chorus {req.chorus_call_id}", "Internal Drive collateral"],
    )

    row = svc.draft_or_send(
        to=req.to,
        cc=req.cc,
        subject=subject,
        body=body,
        requested_mode=req.mode,
        chorus_call_id=req.chorus_call_id,
        artifact_id=artifact.id,
    )

    output = {
        "mode": row.mode.value,
        "channel": row.channel.value,
        "to": row.to_recipients,
        "cc": row.cc_recipients,
        "subject": row.subject,
        "body": row.body,
        "reason_blocked": row.reason_blocked,
    }

    write_audit_log(
        db,
        actor=call.rep_email,
        action="draft_message" if row.mode.value == "draft" else "send_message",
        input_payload=req.model_dump(),
        retrieval_payload={},
        output_payload=output,
        status=AuditStatus.OK,
    )
    return output
