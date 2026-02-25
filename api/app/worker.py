from __future__ import annotations

from datetime import date

from celery import Celery

from app.core.settings import get_settings
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.ingest.drive_ingestor import DriveIngestor
from app.ingest.transcript_ingestor import TranscriptIngestor

settings = get_settings()
celery_app = Celery("tidb_oracle", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    beat_schedule={
        "daily-ingestion": {
            "task": "daily_ingestion",
            "schedule": 24 * 60 * 60,
        }
    },
)


@celery_app.task(name="sync_drive")
def sync_drive_task(since: str | None = None) -> dict:
    init_db()
    from dateutil.parser import isoparse

    since_dt = isoparse(since) if since else None
    with SessionLocal() as db:
        return DriveIngestor(db).sync(since=since_dt)


@celery_app.task(name="sync_chorus")
def sync_chorus_task(since: str | None = None) -> dict:
    init_db()
    since_date = date.fromisoformat(since) if since else None
    with SessionLocal() as db:
        return TranscriptIngestor(db).sync(since=since_date)


@celery_app.task(name="daily_ingestion")
def daily_ingestion_task() -> dict:
    init_db()
    with SessionLocal() as db:
        drive = DriveIngestor(db).sync()
        chorus = TranscriptIngestor(db).sync()
    return {"drive": drive, "chorus": chorus}
