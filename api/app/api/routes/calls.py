from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import db_session
from app.models import AuditStatus, CallArtifact, ChorusCall, KBDocument, KBChunk
from app.schemas.messaging import RegenerateDraftRequest
from app.services.audit import write_audit_log
from app.services.messaging import MessagingService

router = APIRouter()


@router.get("")
def list_calls(
    account: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(db_session),
) -> list[dict]:
    stmt = select(ChorusCall).order_by(ChorusCall.date.desc()).limit(limit)
    if account:
        stmt = stmt.where(ChorusCall.account == account)

    calls = db.execute(stmt).scalars().all()
    return [
        {
            "chorus_call_id": c.chorus_call_id,
            "date": c.date,
            "account": c.account,
            "opportunity": c.opportunity,
            "stage": c.stage,
            "rep_email": c.rep_email,
            "se_email": c.se_email,
        }
        for c in calls
    ]


@router.get("/{chorus_call_id}")
def call_detail(chorus_call_id: str, db: Session = Depends(db_session)) -> dict:
    call = db.execute(select(ChorusCall).where(ChorusCall.chorus_call_id == chorus_call_id)).scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="call not found")

    artifact = db.execute(
        select(CallArtifact).where(CallArtifact.chorus_call_id == chorus_call_id).order_by(CallArtifact.created_at.desc())
    ).scalars().first()

    doc = db.execute(select(KBDocument).where(KBDocument.source_id == chorus_call_id)).scalar_one_or_none()
    chunks: list[KBChunk] = []
    if doc:
        chunks = db.execute(
            select(KBChunk).where(KBChunk.document_id == doc.id).order_by(KBChunk.chunk_index.asc())
        ).scalars().all()

    return {
        "call": {
            "chorus_call_id": call.chorus_call_id,
            "date": call.date,
            "account": call.account,
            "opportunity": call.opportunity,
            "stage": call.stage,
            "rep_email": call.rep_email,
            "se_email": call.se_email,
            "participants": call.participants,
            "recording_url": call.recording_url,
            "transcript_url": call.transcript_url,
        },
        "artifact": {
            "id": str(artifact.id),
            "summary": artifact.summary,
            "objections": artifact.objections,
            "competitors_mentioned": artifact.competitors_mentioned,
            "risks": artifact.risks,
            "next_steps": artifact.next_steps,
            "recommended_collateral": artifact.recommended_collateral,
            "follow_up_questions": artifact.follow_up_questions,
        }
        if artifact
        else None,
        "chunks": [
            {
                "chunk_id": str(chunk.id),
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "metadata": chunk.metadata_json,
            }
            for chunk in chunks
        ],
    }


@router.post("/{chorus_call_id}/regenerate-draft")
def regenerate_draft(
    chorus_call_id: str,
    req: RegenerateDraftRequest,
    db: Session = Depends(db_session),
) -> dict:
    call = db.execute(select(ChorusCall).where(ChorusCall.chorus_call_id == chorus_call_id)).scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="call not found")

    artifact = db.execute(
        select(CallArtifact).where(CallArtifact.chorus_call_id == chorus_call_id).order_by(CallArtifact.created_at.desc())
    ).scalars().first()
    if not artifact:
        raise HTTPException(status_code=404, detail="artifact not found")

    to = req.to or [call.rep_email]
    cc = req.cc or ([call.se_email] if call.se_email else [])
    svc = MessagingService(db)
    subject = svc.build_email_subject(call.account)
    body = svc.build_email_body(
        account=call.account,
        summary=artifact.summary,
        next_steps=artifact.next_steps,
        questions=artifact.follow_up_questions,
        collateral=artifact.recommended_collateral,
        sources=[f"Chorus {chorus_call_id}", "Internal Drive collateral"],
    )
    row = svc.draft_or_send(
        to=to,
        cc=cc,
        subject=subject,
        body=body,
        requested_mode=req.mode,
        chorus_call_id=chorus_call_id,
        artifact_id=artifact.id,
    )
    output = {
        "mode": row.mode.value,
        "to": row.to_recipients,
        "cc": row.cc_recipients,
        "subject": row.subject,
        "body": row.body,
        "reason_blocked": row.reason_blocked,
    }
    write_audit_log(
        db,
        actor=call.rep_email,
        action="draft_message",
        input_payload={"chorus_call_id": chorus_call_id, **req.model_dump()},
        retrieval_payload={},
        output_payload=output,
        status=AuditStatus.OK,
    )
    return output
