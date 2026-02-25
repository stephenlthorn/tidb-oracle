from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session

from app.db.session import get_db


# FastAPI dependency wrapper

def db_session() -> Generator[Session, None, None]:
    yield from get_db()
