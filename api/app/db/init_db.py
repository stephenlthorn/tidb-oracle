from __future__ import annotations

from sqlalchemy import text

from app.db.base import Base
from app.db.session import engine


def init_db(create_extension: bool = True) -> None:
    with engine.begin() as conn:
        if create_extension:
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            except Exception:
                # Non-Postgres backends (e.g., sqlite tests) do not support extensions.
                pass
        Base.metadata.create_all(bind=conn)
