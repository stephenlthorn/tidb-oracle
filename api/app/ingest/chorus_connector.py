from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx

from app.core.settings import get_settings


def _project_root() -> Path:
    here = Path(__file__).resolve()
    candidates = [here.parents[3], here.parents[2], Path.cwd()]
    for base in candidates:
        if (base / "data").exists():
            return base
    return here.parents[3]


@dataclass
class ChorusCallRaw:
    chorus_call_id: str
    payload: dict


class ChorusConnector:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.fake_dir = _project_root() / "data" / "fake_chorus"

    def fetch_calls(self, since: date | None = None) -> list[ChorusCallRaw]:
        if self.settings.chorus_api_key and self.settings.chorus_base_url:
            return self._fetch_calls_api(since)
        return self._fetch_calls_fake(since)

    def _fetch_calls_fake(self, since: date | None = None) -> list[ChorusCallRaw]:
        out: list[ChorusCallRaw] = []
        for path in sorted(self.fake_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            call_date = date.fromisoformat(payload.get("metadata", {}).get("date"))
            if since and call_date <= since:
                continue
            out.append(ChorusCallRaw(chorus_call_id=payload["chorus_call_id"], payload=payload))
        return out

    def _fetch_calls_api(self, since: date | None = None) -> list[ChorusCallRaw]:
        headers = {"Authorization": f"Bearer {self.settings.chorus_api_key}"}
        params = {}
        if since:
            params["since"] = since.isoformat()

        url = f"{self.settings.chorus_base_url.rstrip('/')}/calls"
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, headers=headers, params=params)
            response.raise_for_status()
            payload = response.json()

        calls = payload.get("calls", [])
        out: list[ChorusCallRaw] = []
        for call in calls:
            call_id = call.get("chorus_call_id") or call.get("id")
            if not call_id:
                continue
            out.append(ChorusCallRaw(chorus_call_id=call_id, payload=call))
        return out
