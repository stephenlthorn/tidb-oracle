#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "data" / "fake_drive"
TARGET.mkdir(parents=True, exist_ok=True)

TEMPLATE = """# GTM Enablement Note {idx}

## Scenario
Account {idx} evaluates distributed SQL for mixed transactional and analytical workloads around {size}TB.

## Positioning
- Focus on operational simplicity and online schema change confidence.
- Frame TiDB strengths with workload-specific evidence.
- Identify decision criteria: latency, cost, and operational overhead.

## Discovery Questions
- What are top latency-sensitive queries?
- How often are schema changes required?
- What HA and recovery constraints apply?
"""

for i in range(1, 61):
    size = 10 + i
    path = TARGET / f"gtm_note_{i:02d}.md"
    path.write_text(TEMPLATE.format(idx=i, size=size), encoding="utf-8")

print(f"Generated 60 docs in {TARGET}")
