from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import db_session
from app.models import AuditStatus
from app.schemas.gtm_modules import (
    SEArchitectureFitRequest,
    SEArchitectureFitResponse,
    SECompetitorCoachRequest,
    SECompetitorCoachResponse,
    SEPocPlanRequest,
    SEPocPlanResponse,
    SEPocReadinessRequest,
    SEPocReadinessResponse,
)
from app.services.audit import write_audit_log
from app.services.gtm_modules import GTMModuleService

router = APIRouter()


def _ensure_enabled(service: GTMModuleService, key: str) -> None:
    if not service.module_enabled(key):
        raise HTTPException(status_code=403, detail=f"Module '{key}' is disabled by feature flags.")


@router.post("/poc-plan", response_model=SEPocPlanResponse)
def se_poc_plan(req: SEPocPlanRequest, request: Request, db: Session = Depends(db_session)) -> dict:
    openai_token = request.headers.get("X-OpenAI-Token")
    service = GTMModuleService(db, openai_token=openai_token)
    _ensure_enabled(service, "se_poc_plan")
    try:
        data, retrieval = service.se_poc_plan(
            user=req.user,
            account=req.account,
            chorus_call_id=req.chorus_call_id,
            target_offering=req.target_offering,
        )
        write_audit_log(
            db,
            actor=req.user,
            action="se_poc_plan",
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
            action="se_poc_plan",
            input_payload=req.model_dump(),
            retrieval_payload={},
            output_payload={},
            status=AuditStatus.ERROR,
            error_message=str(exc),
        )
        raise


@router.post("/poc-readiness", response_model=SEPocReadinessResponse)
def se_poc_readiness(req: SEPocReadinessRequest, request: Request, db: Session = Depends(db_session)) -> dict:
    openai_token = request.headers.get("X-OpenAI-Token")
    service = GTMModuleService(db, openai_token=openai_token)
    _ensure_enabled(service, "se_poc_readiness")
    try:
        data, retrieval = service.se_poc_readiness(
            user=req.user,
            account=req.account,
            chorus_call_id=req.chorus_call_id,
        )
        write_audit_log(
            db,
            actor=req.user,
            action="se_poc_readiness",
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
            action="se_poc_readiness",
            input_payload=req.model_dump(),
            retrieval_payload={},
            output_payload={},
            status=AuditStatus.ERROR,
            error_message=str(exc),
        )
        raise


@router.post("/architecture-fit", response_model=SEArchitectureFitResponse)
def se_architecture_fit(req: SEArchitectureFitRequest, request: Request, db: Session = Depends(db_session)) -> dict:
    openai_token = request.headers.get("X-OpenAI-Token")
    service = GTMModuleService(db, openai_token=openai_token)
    _ensure_enabled(service, "se_architecture_fit")
    try:
        data, retrieval = service.se_architecture_fit(
            user=req.user,
            account=req.account,
            chorus_call_id=req.chorus_call_id,
        )
        write_audit_log(
            db,
            actor=req.user,
            action="se_architecture_fit",
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
            action="se_architecture_fit",
            input_payload=req.model_dump(),
            retrieval_payload={},
            output_payload={},
            status=AuditStatus.ERROR,
            error_message=str(exc),
        )
        raise


@router.post("/competitor-coach", response_model=SECompetitorCoachResponse)
def se_competitor_coach(req: SECompetitorCoachRequest, request: Request, db: Session = Depends(db_session)) -> dict:
    openai_token = request.headers.get("X-OpenAI-Token")
    service = GTMModuleService(db, openai_token=openai_token)
    _ensure_enabled(service, "se_competitor_coach")
    try:
        data, retrieval = service.se_competitor_coach(
            user=req.user,
            account=req.account,
            chorus_call_id=req.chorus_call_id,
            competitor=req.competitor,
        )
        write_audit_log(
            db,
            actor=req.user,
            action="se_competitor_coach",
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
            action="se_competitor_coach",
            input_payload=req.model_dump(),
            retrieval_payload={},
            output_payload={},
            status=AuditStatus.ERROR,
            error_message=str(exc),
        )
        raise
