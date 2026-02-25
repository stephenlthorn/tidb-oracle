from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure settings resolve to a local sqlite database for tests.
TEST_DB = Path(__file__).resolve().parent / "test.db"
os.environ.setdefault("DATABASE_URL", f"sqlite+pysqlite:///{TEST_DB}")
os.environ.setdefault("AUTO_CREATE_SCHEMA", "true")
os.environ.setdefault("OPENAI_API_KEY", "")

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def db_session():
    with SessionLocal() as db:
        yield db


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
