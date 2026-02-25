#!/usr/bin/env python3
"""Seed a SQLite MVP database with TiDB docs and fake Chorus calls."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "api"
DEFAULT_DB_PATH = ROOT / "data" / "tidb_oracle_mvp.sqlite3"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed SQLite MVP data for TiDB Oracle.")
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help="Absolute path to SQLite database file.",
    )
    parser.add_argument(
        "--all-drive-files",
        action="store_true",
        help="Index all fake drive files (default is docs-only subset for faster MVP setup).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db_path).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{db_path}"
    os.environ.setdefault("FAKE_DRIVE_INCLUDE_GITHUB", "true")

    # Ensure local imports resolve from the API package.
    sys.path.insert(0, str(API_DIR))

    from sqlalchemy import func, select

    from app.db.init_db import init_db
    from app.db.session import SessionLocal
    from app.ingest.drive_ingestor import DriveIngestor
    from app.ingest.transcript_ingestor import TranscriptIngestor
    from app.models import ChorusCall, KBDocument, KBChunk

    if db_path.exists():
        db_path.unlink()

    init_db(create_extension=False)

    with SessionLocal() as db:
        drive = DriveIngestor(db)
        original_list_files = drive.connector.list_files

        def docs_only(since=None):
            files = original_list_files(since)
            if args.all_drive_files:
                return files
            return [
                f
                for f in files
                if f.title.startswith("github/pingcap__docs/") or f.title == "tidb-online-ddl-guidelines.md"
            ]

        drive.connector.list_files = docs_only  # type: ignore[method-assign]
        drive_result = drive.sync(since=None)

    with SessionLocal() as db:
        transcript_result = TranscriptIngestor(db).sync(since=None)

    with SessionLocal() as db:
        doc_count = db.execute(select(func.count()).select_from(KBDocument)).scalar_one()
        chunk_count = db.execute(select(func.count()).select_from(KBChunk)).scalar_one()
        call_count = db.execute(select(func.count()).select_from(ChorusCall)).scalar_one()

    print(
        json.dumps(
            {
                "database_url": os.environ["DATABASE_URL"],
                "drive": drive_result,
                "transcripts": transcript_result,
                "documents": doc_count,
                "chunks": chunk_count,
                "calls": call_count,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
