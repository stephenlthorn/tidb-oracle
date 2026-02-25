# TiFlash Sizing Pitfalls

TiFlash can accelerate analytical patterns, but early overprovisioning or underprovisioning increases cost or risks lag.

## Common Pitfalls

- Enabling TiFlash replicas before query patterns are validated.
- Ignoring replication lag when ingest spikes occur.
- Treating all analytical tables equally without ranking by business criticality.

## Recommendations

- Start with critical datasets and staged replica rollout.
- Define acceptable lag windows tied to user-facing workloads.
- Measure p95/p99 query latency and adjust replica strategy iteratively.
