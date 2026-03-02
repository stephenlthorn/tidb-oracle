from __future__ import annotations

from pathlib import Path


def test_memory_source_type_migration_exists_and_adds_enum_value():
    repo_root = Path(__file__).resolve().parents[2]
    migration_path = repo_root / "api" / "alembic" / "versions" / "20260302_000005_add_memory_source_type_enum.py"
    assert migration_path.exists(), "Missing migration for SourceType.MEMORY enum value."

    content = migration_path.read_text(encoding="utf-8")
    assert "ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'memory'" in content
