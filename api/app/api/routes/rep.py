from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import db_session
from app.models import AuditStatus
from app.schemas.gtm_modules import (
    RepAccountBriefRequest,
    RepAccountBriefResponse,
    RepDealRiskRequest,
    RepDealRiskResponse,
    RepDiscoveryQuestionsRequest,
    RepDiscoveryQuestionsResponse,
    RepFollowUpDraftRequest,
    RepFollowUpDraftResponse,
)
from app.schemas.market_research import MarketResearchRequest, MarketResearchResponse
from app.services.audit import write_audit_log
from app.services.gtm_modules import GTMModuleService
from app.services.market_research import MarketResearchService

router = APIRouter()


def _ensure_enabled(service: GTMModuleService, key: str) -> None:
    if not service.module_enabled(key):
        raise HTTPException(status_code=403, detail=f"Module '{key}' is disabled by feature flags.")


@router.post("/market-research", response_model=MarketResearchResponse)
def market_research(
    req: MarketResearchRequest,
    request: Request,
    db: Session = Depends(db_session),
) -> dict:
    openai_token = request.headers.get("X-OpenAI-Token") or req.openai_token
    service = MarketResearchService(db, openai_token=openai_token)

    try:
        data, parse_meta = service.generate(req)
        write_audit_log(
            db,
            actor=req.user,
            action="market_research",
            input_payload=req.model_dump(exclude={"openai_token"}),
            retrieval_payload=parse_meta,
            output_payload=data,
            status=AuditStatus.OK,
        )
        return data
    except Exception as exc:
        db.rollback()
        write_audit_log(
            db,
            actor=req.user,
            action="market_research",
            input_payload=req.model_dump(exclude={"openai_token"}),
            retrieval_payload={},
            output_payload={},
            status=AuditStatus.ERROR,
            error_message=str(exc),
        )
        raise


@router.post("/account-brief", response_model=RepAccountBriefResponse)
def rep_account_brief(
    req: RepAccountBriefRequest,
    request: Request,
    db: Session = Depends(db_session),
) -> dict:
    openai_token = request.headers.get("X-OpenAI-Token")
    service = GTMModuleService(db, openai_token=openai_token)
    _ensure_enabled(service, "rep_account_brief")
    try:
        data, retrieval = service.rep_account_brief(
            user=req.user,
            account=req.account,
            chorus_call_id=req.chorus_call_id,
        )
        write_audit_log(
            db,
            actor=req.user,
            action="rep_account_brief",
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
            action="rep_account_brief",
            input_payload=req.model_dump(),
            retrieval_payload={},
            output_payload={},
            status=AuditStatus.ERROR,
            error_message=str(exc),
        )
        raise


@router.post("/discovery-questions", response_model=RepDiscoveryQuestionsResponse)
def rep_discovery_questions(
    req: RepDiscoveryQuestionsRequest,
    request: Request,
    db: Session = Depends(db_session),
) -> dict:
    openai_token = request.headers.get("X-OpenAI-Token")
    service = GTMModuleService(db, openai_token=openai_token)
    _ensure_enabled(service, "rep_discovery_questions")
    try:
        data, retrieval = service.rep_discovery_questions(
            user=req.user,
            account=req.account,
            chorus_call_id=req.chorus_call_id,
            count=req.count,
        )
        write_audit_log(
            db,
            actor=req.user,
            action="rep_discovery_questions",
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
            action="rep_discovery_questions",
            input_payload=req.model_dump(),
            retrieval_payload={},
            output_payload={},
            status=AuditStatus.ERROR,
            error_message=str(exc),
        )
        raise


@router.post("/follow-up-draft", response_model=RepFollowUpDraftResponse)
def rep_follow_up_draft(
    req: RepFollowUpDraftRequest,
    request: Request,
    db: Session = Depends(db_session),
) -> dict:
    openai_token = request.headers.get("X-OpenAI-Token")
    service = GTMModuleService(db, openai_token=openai_token)
    _ensure_enabled(service, "rep_follow_up_draft")
    try:
        data, retrieval = service.rep_follow_up_draft(
            user=req.user,
            account=req.account,
            chorus_call_id=req.chorus_call_id,
            requested_mode=req.mode,
            to=req.to,
            cc=req.cc,
            tone=req.tone,
        )
        write_audit_log(
            db,
            actor=req.user,
            action="rep_follow_up_draft",
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
            action="rep_follow_up_draft",
            input_payload=req.model_dump(),
            retrieval_payload={},
            output_payload={},
            status=AuditStatus.ERROR,
            error_message=str(exc),
        )
        raise


@router.post("/deal-risk", response_model=RepDealRiskResponse)
def rep_deal_risk(
    req: RepDealRiskRequest,
    request: Request,
    db: Session = Depends(db_session),
) -> dict:
    openai_token = request.headers.get("X-OpenAI-Token")
    service = GTMModuleService(db, openai_token=openai_token)
    _ensure_enabled(service, "rep_deal_risk")
    try:
        data, retrieval = service.rep_deal_risk(
            user=req.user,
            account=req.account,
            chorus_call_id=req.chorus_call_id,
        )
        write_audit_log(
            db,
            actor=req.user,
            action="rep_deal_risk",
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
            action="rep_deal_risk",
            input_payload=req.model_dump(),
            retrieval_payload={},
            output_payload={},
            status=AuditStatus.ERROR,
            error_message=str(exc),
        )
        raise
