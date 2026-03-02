from __future__ import annotations

from datetime import date
import re

import httpx
from dateutil.parser import isoparse
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import db_session
from app.core.settings import get_settings
from app.ingest.drive_ingestor import DriveIngestor
from app.ingest.feishu_ingestor import FeishuIngestor
from app.ingest.transcript_ingestor import TranscriptIngestor
from app.models import AuditLog, AuditStatus, KBConfig
from app.prompts.personas import normalize_persona
from app.schemas.kb_config import KBConfigRead, KBConfigUpdate
from app.services.audit import write_audit_log
from app.services.google_drive_credentials import GoogleDriveCredentialService
from app.services.google_drive_oauth import google_drive_oauth_state_store
from app.services.feishu_credentials import FeishuCredentialService
from app.services.feishu_oauth import feishu_oauth_state_store
from app.services.drive_sync_jobs import drive_sync_jobs

router = APIRouter()


def _request_user_email(request: Request, fallback: str | None = None) -> str | None:
    raw = (request.headers.get("X-User-Email") if request else "") or fallback or ""
    email = raw.strip().lower()
    return email or None


def _parse_token_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    parts = re.split(r"[,\n\r\t ]+", raw)
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        token = part.strip()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _resolve_feishu_roots(config: KBConfig | None) -> list[str]:
    roots = _parse_token_list(config.feishu_root_tokens if config else None)
    legacy = (config.feishu_folder_token if config else "") or ""
    legacy = legacy.strip()
    if legacy and legacy not in roots:
        roots.append(legacy)
    return roots


def _resolve_feishu_creds(config: KBConfig | None) -> tuple[str, str]:
    settings = get_settings()
    app_id = ((config.feishu_app_id if config else None) or settings.feishu_app_id or "").strip()
    app_secret = ((config.feishu_app_secret if config else None) or settings.feishu_app_secret or "").strip()
    return app_id, app_secret


def _feishu_scopes() -> list[str]:
    settings = get_settings()
    raw = (settings.feishu_oauth_scopes or "").strip()
    scopes = [scope.strip() for scope in raw.split(" ") if scope.strip()]
    if not scopes:
        scopes = ["offline_access", "drive:drive:readonly", "docs:document:readonly"]
    return scopes


def _exchange_feishu_oauth_code(*, app_id: str, app_secret: str, code: str, redirect_uri: str) -> dict:
    settings = get_settings()
    headers = {
        "Authorization": f"Bearer {app_id}:{app_secret}",
        "Content-Type": "application/json; charset=utf-8",
    }
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }
    endpoints = ["/authen/v1/oidc/access_token", "/authen/v1/access_token"]
    errors: list[str] = []
    for endpoint in endpoints:
        url = f"{settings.feishu_base_url.rstrip('/')}{endpoint}"
        try:
            res = httpx.post(url, headers=headers, json=body, timeout=20.0)
            if res.status_code >= 400:
                errors.append(f"{endpoint}:HTTP{res.status_code}")
                continue
            payload = res.json()
            if payload.get("code") != 0:
                errors.append(f"{endpoint}:{payload.get('msg') or payload.get('code')}")
                continue
            data = payload.get("data") or {}
            if data.get("access_token"):
                return data
            errors.append(f"{endpoint}:missing_access_token")
        except Exception as exc:
            errors.append(f"{endpoint}:{exc}")
    raise RuntimeError(f"Feishu token exchange failed ({'; '.join(errors)})")


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
    request: Request,
    since: str | None = Query(default=None, description="ISO timestamp"),
    db: Session = Depends(db_session),
) -> dict:
    user_email = _request_user_email(request)
    since_dt = isoparse(since) if since else None
    ingestor = DriveIngestor(db)
    result = ingestor.sync(since=since_dt, user_email=user_email)
    write_audit_log(
        db,
        actor=user_email or "system",
        action="sync_drive",
        input_payload={"since": since, "user_email": user_email},
        retrieval_payload={},
        output_payload=result,
        status=AuditStatus.OK,
    )
    return result


@router.post("/sync/drive/start")
def sync_drive_start(
    request: Request,
    since: str | None = Query(default=None, description="ISO timestamp"),
) -> dict:
    user_email = _request_user_email(request)
    return drive_sync_jobs.start(since, user_email=user_email)


@router.get("/sync/drive/jobs/latest")
def sync_drive_latest_job(request: Request) -> dict:
    user_email = _request_user_email(request)
    job = drive_sync_jobs.latest(user_email=user_email)
    return {"job": job}


@router.get("/sync/drive/jobs/{job_id}")
def sync_drive_job_status(job_id: str, request: Request) -> dict:
    user_email = _request_user_email(request)
    job = drive_sync_jobs.get(job_id)
    if not job:
        return {"job": None}
    if (job.get("user_email") or None) != (user_email or None):
        return {"job": None}
    return {"job": job}


@router.get("/sync/drive/jobs")
def sync_drive_jobs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    user_email = _request_user_email(request)
    return {"jobs": drive_sync_jobs.list(limit=limit, user_email=user_email)}


@router.get("/drive/oauth/start")
def drive_oauth_start(
    request: Request,
    redirect_uri: str = Query(...),
) -> dict:
    settings = get_settings()
    user_email = _request_user_email(request)
    if not user_email:
        raise HTTPException(status_code=400, detail="Missing signed-in user email.")
    if not settings.google_drive_client_id or not settings.google_drive_client_secret:
        raise HTTPException(
            status_code=500,
            detail="Google Drive OAuth client is not configured. Set GOOGLE_DRIVE_CLIENT_ID and GOOGLE_DRIVE_CLIENT_SECRET.",
        )
    payload = google_drive_oauth_state_store.create_auth_url(user_email=user_email, redirect_uri=redirect_uri)
    return {"auth_url": payload["auth_url"]}


@router.post("/drive/oauth/exchange")
def drive_oauth_exchange(
    request: Request,
    body: dict | None = Body(default=None),
    db: Session = Depends(db_session),
) -> dict:
    settings = get_settings()
    payload = body or {}
    user_email = _request_user_email(request, fallback=payload.get("user_email"))
    if not user_email:
        raise HTTPException(status_code=400, detail="Missing signed-in user email.")
    code = str(payload.get("code") or "").strip()
    state = str(payload.get("state") or "").strip()
    redirect_uri = str(payload.get("redirect_uri") or "").strip()
    if not code or not state or not redirect_uri:
        raise HTTPException(status_code=400, detail="code, state, and redirect_uri are required.")

    if not settings.google_drive_client_id or not settings.google_drive_client_secret:
        raise HTTPException(status_code=500, detail="Google Drive OAuth client is not configured.")

    try:
        pending = google_drive_oauth_state_store.consume(
            state=state,
            user_email=user_email,
            redirect_uri=redirect_uri,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    token_form = {
        "code": code,
        "client_id": settings.google_drive_client_id,
        "client_secret": settings.google_drive_client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": pending.verifier,
    }
    token_res = httpx.post("https://oauth2.googleapis.com/token", data=token_form, timeout=20.0)
    if token_res.status_code >= 400:
        raise HTTPException(status_code=token_res.status_code, detail=f"Google token exchange failed: {token_res.text[:400]}")
    token_payload = token_res.json()

    cred_service = GoogleDriveCredentialService(db)
    previous = cred_service.get_stored_payload(user_email) or {}
    previous_refresh = previous.get("refresh_token")

    stored_payload = cred_service.token_payload_from_oauth_exchange(token_payload)
    if not stored_payload.get("refresh_token") and previous_refresh:
        stored_payload["refresh_token"] = previous_refresh
    cred_service.upsert_token_payload(user_email, stored_payload, commit=True)

    write_audit_log(
        db,
        actor=user_email,
        action="drive_oauth_exchange",
        input_payload={"user_email": user_email},
        retrieval_payload={},
        output_payload={"connected": True},
        status=AuditStatus.OK,
    )
    return {"connected": True}


@router.get("/drive/status")
def drive_status(request: Request, db: Session = Depends(db_session)) -> dict:
    user_email = _request_user_email(request)
    if not user_email:
        raise HTTPException(status_code=400, detail="Missing signed-in user email.")
    status = GoogleDriveCredentialService(db).get_status(user_email)
    return status


@router.delete("/drive/credentials")
def drive_disconnect(request: Request, db: Session = Depends(db_session)) -> dict:
    user_email = _request_user_email(request)
    if not user_email:
        raise HTTPException(status_code=400, detail="Missing signed-in user email.")
    deleted = GoogleDriveCredentialService(db).delete_for_user(user_email, commit=True)
    write_audit_log(
        db,
        actor=user_email,
        action="drive_oauth_disconnect",
        input_payload={"user_email": user_email},
        retrieval_payload={},
        output_payload={"deleted": deleted},
        status=AuditStatus.OK,
    )
    return {"connected": False, "deleted": deleted}


@router.get("/feishu/oauth/start")
def feishu_oauth_start(
    request: Request,
    redirect_uri: str = Query(...),
    db: Session = Depends(db_session),
) -> dict:
    user_email = _request_user_email(request)
    if not user_email:
        raise HTTPException(status_code=400, detail="Missing signed-in user email.")

    kb_config: KBConfig | None = db.get(KBConfig, 1)
    app_id, app_secret = _resolve_feishu_creds(kb_config)
    if not app_id or not app_secret:
        raise HTTPException(
            status_code=500,
            detail="Feishu OAuth app is not configured. Set feishu_app_id and feishu_app_secret.",
        )

    payload = feishu_oauth_state_store.create_auth_url(
        user_email=user_email,
        redirect_uri=redirect_uri,
        app_id=app_id,
        scopes=_feishu_scopes(),
    )
    return {"auth_url": payload["auth_url"]}


@router.post("/feishu/oauth/exchange")
def feishu_oauth_exchange(
    request: Request,
    body: dict | None = Body(default=None),
    db: Session = Depends(db_session),
) -> dict:
    payload = body or {}
    user_email = _request_user_email(request, fallback=payload.get("user_email"))
    if not user_email:
        raise HTTPException(status_code=400, detail="Missing signed-in user email.")
    code = str(payload.get("code") or "").strip()
    state = str(payload.get("state") or "").strip()
    redirect_uri = str(payload.get("redirect_uri") or "").strip()
    if not code or not state or not redirect_uri:
        raise HTTPException(status_code=400, detail="code, state, and redirect_uri are required.")

    kb_config: KBConfig | None = db.get(KBConfig, 1)
    app_id, app_secret = _resolve_feishu_creds(kb_config)
    if not app_id or not app_secret:
        raise HTTPException(status_code=500, detail="Feishu OAuth app is not configured.")

    try:
        feishu_oauth_state_store.consume(
            state=state,
            user_email=user_email,
            redirect_uri=redirect_uri,
            app_id=app_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        token_data = _exchange_feishu_oauth_code(
            app_id=app_id,
            app_secret=app_secret,
            code=code,
            redirect_uri=redirect_uri,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    cred_service = FeishuCredentialService(db)
    previous = cred_service.get_stored_payload(user_email) or {}
    previous_refresh = previous.get("refresh_token")
    stored_payload = FeishuCredentialService.token_payload_from_oauth_exchange(token_data)
    if not stored_payload.get("refresh_token") and previous_refresh:
        stored_payload["refresh_token"] = previous_refresh
    cred_service.upsert_token_payload(user_email, stored_payload, commit=True)

    write_audit_log(
        db,
        actor=user_email,
        action="feishu_oauth_exchange",
        input_payload={"user_email": user_email},
        retrieval_payload={},
        output_payload={"connected": True},
        status=AuditStatus.OK,
    )
    return {"connected": True}


@router.get("/feishu/status")
def feishu_status(request: Request, db: Session = Depends(db_session)) -> dict:
    user_email = _request_user_email(request)
    if not user_email:
        raise HTTPException(status_code=400, detail="Missing signed-in user email.")
    return FeishuCredentialService(db).get_status(user_email)


@router.delete("/feishu/credentials")
def feishu_disconnect(request: Request, db: Session = Depends(db_session)) -> dict:
    user_email = _request_user_email(request)
    if not user_email:
        raise HTTPException(status_code=400, detail="Missing signed-in user email.")
    deleted = FeishuCredentialService(db).delete_for_user(user_email, commit=True)
    write_audit_log(
        db,
        actor=user_email,
        action="feishu_oauth_disconnect",
        input_payload={"user_email": user_email},
        retrieval_payload={},
        output_payload={"deleted": deleted},
        status=AuditStatus.OK,
    )
    return {"connected": False, "deleted": deleted}


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
    normalized_persona = normalize_persona(config.persona_name)
    if normalized_persona != config.persona_name:
        config.persona_name = normalized_persona
        db.add(config)
        db.commit()
        db.refresh(config)
    if config.feature_flags_json is None:
        config.feature_flags_json = {}
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


@router.put("/kb-config", response_model=KBConfigRead)
def update_kb_config(update: KBConfigUpdate, db: Session = Depends(db_session)):
    config = db.get(KBConfig, 1)
    if config is None:
        config = KBConfig(id=1)
    payload = update.model_dump(exclude_none=True)
    if "persona_name" in payload:
        payload["persona_name"] = normalize_persona(payload.get("persona_name"))
    if "persona_prompt" in payload:
        prompt = (payload.get("persona_prompt") or "").strip()
        payload["persona_prompt"] = prompt or None
    if "feishu_root_tokens" in payload:
        roots = _parse_token_list(payload.get("feishu_root_tokens"))
        payload["feishu_root_tokens"] = "\n".join(roots) if roots else None
    if "feishu_folder_token" in payload:
        token = (payload.get("feishu_folder_token") or "").strip()
        payload["feishu_folder_token"] = token or None
    if "feishu_app_id" in payload:
        app_id = (payload.get("feishu_app_id") or "").strip()
        payload["feishu_app_id"] = app_id or None
    if "feishu_app_secret" in payload:
        secret = (payload.get("feishu_app_secret") or "").strip()
        payload["feishu_app_secret"] = secret or None
    if "se_poc_kit_url" in payload:
        url = (payload.get("se_poc_kit_url") or "").strip()
        payload["se_poc_kit_url"] = url or None
    if "feature_flags_json" in payload:
        flags = payload.get("feature_flags_json") or {}
        payload["feature_flags_json"] = flags if isinstance(flags, dict) else {}

    for field, value in payload.items():
        setattr(config, field, value)
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@router.post("/sync/feishu")
def sync_feishu(request: Request, db: Session = Depends(db_session)) -> dict:
    settings = get_settings()
    kb_config: KBConfig | None = db.get(KBConfig, 1)
    user_email = _request_user_email(request)
    app_id, app_secret = _resolve_feishu_creds(kb_config)
    roots = _resolve_feishu_roots(kb_config)
    global_mode = False
    if not roots:
        # Global mode: list all Feishu files visible to the current token.
        roots = [""]
        global_mode = True

    oauth_mode = bool(kb_config.feishu_oauth_enabled if kb_config else False)
    cred_service = FeishuCredentialService(db)

    if oauth_mode:
        if not user_email:
            return {
                "status": "error",
                "message": "Missing signed-in user email for Feishu OAuth mode.",
            }
        if not app_id or not app_secret:
            return {
                "status": "error",
                "message": "Feishu OAuth app_id / app_secret not configured.",
            }
        try:
            access_token = cred_service.get_access_token(
                user_email,
                app_id=app_id,
                app_secret=app_secret,
                base_url=settings.feishu_base_url,
            )
        except RuntimeError as exc:
            return {
                "status": "error",
                "message": f"Feishu OAuth is not connected for {user_email}. {exc}",
            }
        ingestor = FeishuIngestor(
            db,
            app_id=app_id,
            app_secret=app_secret,
            access_token=access_token,
            user_email=user_email,
        )
    else:
        if not app_id or not app_secret:
            return {"status": "error", "message": "Feishu app_id / app_secret not configured."}
        ingestor = FeishuIngestor(db, app_id=app_id, app_secret=app_secret)

    result = ingestor.sync_roots(roots, recursive=True)
    if oauth_mode and user_email:
        cred_service.update_last_synced(user_email)
    indexed = int(result.get("added", 0)) + int(result.get("updated", 0))
    errors = int(result.get("errors", 0))
    status_value = "ok"
    message: str | None = None
    if errors > 0 and indexed == 0:
        status_value = "error"
        message = "Feishu sync failed due to permissions or content access errors."
    elif errors > 0:
        status_value = "partial"
        message = "Feishu sync completed with some document-level errors."
    write_audit_log(
        db,
        actor=user_email or "system",
        action="sync_feishu",
        input_payload={
            "roots": roots,
            "oauth_mode": oauth_mode,
            "global_mode": global_mode,
            "user_email": user_email,
        },
        retrieval_payload={},
        output_payload=result,
        status=AuditStatus.OK,
    )
    return {"status": status_value, "message": message, **result}
