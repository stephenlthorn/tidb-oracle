from __future__ import annotations

from pathlib import Path


def test_api_dockerfile_does_not_copy_local_service_account_json():
    repo_root = Path(__file__).resolve().parents[2]
    dockerfile = (repo_root / "api" / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY api/service-account.json /app/service-account.json" not in dockerfile
