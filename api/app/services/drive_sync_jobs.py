from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock, Thread
from typing import Any
from uuid import uuid4

from dateutil.parser import isoparse
from fastapi.encoders import jsonable_encoder

from app.db.session import SessionLocal
from app.ingest.drive_ingestor import DriveIngestor
from app.models import AuditStatus
from app.services.audit import write_audit_log


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class DriveSyncJob:
    job_id: str
    status: str
    since: str | None
    user_email: str | None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime | None = None
    progress: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "since": self.since,
            "user_email": self.user_email,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "progress": jsonable_encoder(self.progress or {}),
            "result": jsonable_encoder(self.result) if self.result is not None else None,
            "error": self.error,
        }


class DriveSyncJobManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._jobs: dict[str, DriveSyncJob] = {}
        self._order: list[str] = []
        self._threads: dict[str, Thread] = {}
        self._max_jobs = 50

    def _trim_history(self) -> None:
        if len(self._order) <= self._max_jobs:
            return
        drop_ids = self._order[:-self._max_jobs]
        self._order = self._order[-self._max_jobs :]
        for job_id in drop_ids:
            self._jobs.pop(job_id, None)
            self._threads.pop(job_id, None)

    def _active_job_id(self, user_email: str | None) -> str | None:
        normalized = (user_email or "").strip().lower() or None
        for job_id in reversed(self._order):
            job = self._jobs.get(job_id)
            if not job:
                continue
            if (job.user_email or None) != normalized:
                continue
            if job.status in {"queued", "running"}:
                return job_id
        return None

    def start(self, since: str | None, user_email: str | None = None) -> dict[str, Any]:
        normalized = (user_email or "").strip().lower() or None
        with self._lock:
            active = self._active_job_id(normalized)
            if active:
                existing = self._jobs[active]
                return {
                    "accepted": False,
                    "reason": "already_running",
                    "job": existing.to_dict(),
                }

            job_id = str(uuid4())
            job = DriveSyncJob(
                job_id=job_id,
                status="queued",
                since=since,
                user_email=normalized,
                created_at=_utc_now(),
                updated_at=_utc_now(),
                progress={"phase": "queued"},
            )
            self._jobs[job_id] = job
            self._order.append(job_id)
            self._trim_history()

            thread = Thread(target=self._run_job, args=(job_id,), daemon=True, name=f"drive-sync-{job_id[:8]}")
            self._threads[job_id] = thread
            thread.start()
            return {"accepted": True, "job": job.to_dict()}

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            for k, v in changes.items():
                setattr(job, k, v)
            job.updated_at = _utc_now()

    def _run_job(self, job_id: str) -> None:
        self._update(job_id, status="running", started_at=_utc_now(), progress={"phase": "starting"})
        with self._lock:
            job = self._jobs.get(job_id)
            since_raw = job.since if job else None
            user_email = job.user_email if job else None

        try:
            since_dt = isoparse(since_raw) if since_raw else None
        except Exception as exc:
            msg = f"Invalid 'since' value: {exc}"
            self._update(job_id, status="failed", finished_at=_utc_now(), error=msg, progress={"phase": "failed"})
            with SessionLocal() as db:
                write_audit_log(
                    db,
                    actor=user_email or "system",
                    action="sync_drive_async",
                    input_payload={"since": since_raw, "job_id": job_id, "user_email": user_email},
                    retrieval_payload={},
                    output_payload={},
                    status=AuditStatus.ERROR,
                    error_message=msg,
                )
            return

        try:
            with SessionLocal() as db:
                ingestor = DriveIngestor(db)

                def on_progress(payload: dict[str, Any]) -> None:
                    self._update(job_id, progress=payload)

                result = ingestor.sync(since=since_dt, progress=on_progress, user_email=user_email)
                self._update(job_id, status="completed", finished_at=_utc_now(), result=result, progress={"phase": "completed", **result})

                write_audit_log(
                    db,
                    actor=user_email or "system",
                    action="sync_drive_async",
                    input_payload={"since": since_raw, "job_id": job_id, "user_email": user_email},
                    retrieval_payload={},
                    output_payload=result,
                    status=AuditStatus.OK,
                )
        except Exception as exc:
            msg = str(exc)
            self._update(job_id, status="failed", finished_at=_utc_now(), error=msg, progress={"phase": "failed"})
            try:
                with SessionLocal() as db:
                    write_audit_log(
                        db,
                        actor=user_email or "system",
                        action="sync_drive_async",
                        input_payload={"since": since_raw, "job_id": job_id, "user_email": user_email},
                        retrieval_payload={},
                        output_payload={},
                        status=AuditStatus.ERROR,
                        error_message=msg,
                    )
            except Exception:
                # Do not mask the original job failure if audit logging fails.
                pass

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.to_dict() if job else None

    def latest(self, user_email: str | None = None) -> dict[str, Any] | None:
        normalized = (user_email or "").strip().lower() or None
        with self._lock:
            for job_id in reversed(self._order):
                job = self._jobs.get(job_id)
                if not job:
                    continue
                if (job.user_email or None) != normalized:
                    continue
                return job.to_dict()
            return None

    def list(self, limit: int = 20, user_email: str | None = None) -> list[dict[str, Any]]:
        normalized = (user_email or "").strip().lower() or None
        with self._lock:
            ids = self._order[-max(1, limit) :]
            out: list[dict[str, Any]] = []
            for job_id in reversed(ids):
                job = self._jobs.get(job_id)
                if job and (job.user_email or None) == normalized:
                    out.append(job.to_dict())
            return out


drive_sync_jobs = DriveSyncJobManager()
