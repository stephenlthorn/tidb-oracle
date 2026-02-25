from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2] / "api"))

from app.worker import daily_ingestion_task


if __name__ == "__main__":
    result = daily_ingestion_task.delay()
    print(f"Queued daily ingestion task: {result.id}")
