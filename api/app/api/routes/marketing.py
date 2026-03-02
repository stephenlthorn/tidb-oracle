from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import db_session
from app.models import AuditStatus
from app.schemas.gtm_modules import (
    MarketingFullSolutionRequest,
    MarketingFullSolutionResponse,
    MarketingIntelligenceRequest,
    MarketingIntelligenceResponse,
)
from app.services.audit import write_audit_log
from app.services.gtm_modules import GTMModuleService

router = APIRouter()


@router.post("/intelligence", response_model=MarketingIntelligenceResponse)
def marketing_intelligence(
    req: MarketingIntelligenceRequest,
    request: Request,
    db: Session = Depends(db_session),
) -> dict:
    openai_token = request.headers.get("X-OpenAI-Token")
    service = GTMModuleService(db, openai_token=openai_token)
    if not service.module_enabled("marketing_intelligence"):
        raise HTTPException(status_code=403, detail="Module 'marketing_intelligence' is disabled by feature flags.")
    try:
        data, retrieval = service.marketing_intelligence(
            user=req.user,
            regions=req.regions,
            verticals=req.verticals,
            lookback_days=req.lookback_days,
        )
        write_audit_log(
            db,
            actor=req.user,
            action="marketing_intelligence",
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
            action="marketing_intelligence",
            input_payload=req.model_dump(),
            retrieval_payload={},
            output_payload={},
            status=AuditStatus.ERROR,
            error_message=str(exc),
        )
        raise


@router.post("/full-solution", response_model=MarketingFullSolutionResponse)
def marketing_full_solution(
    req: MarketingFullSolutionRequest,
    request: Request,
    db: Session = Depends(db_session),
) -> dict:
    openai_token = request.headers.get("X-OpenAI-Token")
    service = GTMModuleService(db, openai_token=openai_token)
    if not service.module_enabled("marketing_full_solution"):
        raise HTTPException(status_code=403, detail="Module 'marketing_full_solution' is disabled by feature flags.")
    try:
        data, retrieval = service.marketing_full_solution(
            user=req.user,
            regions=req.regions,
            verticals=req.verticals,
            lookback_days=req.lookback_days,
            campaign_goal=req.campaign_goal,
        )
        write_audit_log(
            db,
            actor=req.user,
            action="marketing_full_solution",
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
            action="marketing_full_solution",
            input_payload=req.model_dump(),
            retrieval_payload={},
            output_payload={},
            status=AuditStatus.ERROR,
            error_message=str(exc),
        )
        raise
