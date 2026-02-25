#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

PYTHONPATH=api python -c "from app.worker import daily_ingestion_task; r = daily_ingestion_task.delay(); print(r.id)"
