# TiDB Online DDL Best Practices

TiDB supports online schema changes through asynchronous DDL jobs. For large tables, monitor DDL progress and schedule heavy schema updates outside peak ETL windows when possible.

## Operational Guidance

- Estimate backfill time using representative row counts and index complexity.
- During online DDL, track TiDB/TiKV resource headroom to avoid user query regressions.
- For business-critical changes, run a dry run in staging with realistic data volume.

## GTM Positioning

When competitors claim faster schema operations, position TiDB around operational safety, controlled rollout, and observability under sustained workload.
