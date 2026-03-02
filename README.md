# tidb-oracle

Internal-only TiDB + PingCAP GTM copilot grounded in Google Drive and Chorus transcripts.

## What this repository provides

- FastAPI backend for RAG chat (`oracle`, `call_assistant`) with citations and follow-up questions.
- Google Drive ingestion pipeline (Docs/PDF/Slides/Sheets-text) into Postgres + pgvector.
- Chorus daily transcript ingestion pipeline with normalization, chunking, and artifact generation.
- Internal-only messaging draft/send workflow with recipient allowlist enforcement.
- Audit logging of prompts, retrieval chunk ids/scores, outputs, timestamps, and mode.
- Minimal Next.js admin UI for docs/transcripts/artifacts/draft regeneration.
- Celery worker + beat for background and daily jobs.
- Synthetic datasets and integration tests.

## Security and policy constraints implemented

- Internal outbound only: all recipients must match `INTERNAL_DOMAIN_ALLOWLIST` (default `pingcap.com`).
- No transcript training/fine-tuning path; only retrieval-time context is used.
- Read-only data connectors (Drive + Chorus).
- Audit log persisted for chat/sync/generation/messaging actions.
- Grounding behavior: if retrieval is weak/empty, chat asks for missing context instead of hallucinating.
- Optional enterprise hardening settings are available to require private LLM endpoints, redact data before provider calls, and fail closed when keys/endpoints are missing.

## Repository layout

```text
/api
  /app
    /api/routes         # FastAPI endpoints
    /core               # settings/constants
    /db                 # SQLAlchemy base/session/init
    /ingest             # Drive + Chorus connectors and ingestors
    /models             # ORM tables
    /prompts            # system prompt templates
    /retrieval          # hybrid retriever (vector + keyword + metadata)
    /schemas            # request/response contracts
    /services           # llm, messaging, audit, orchestration
    /utils              # chunking/hash/guardrails
  /alembic              # migrations
/workers
  /jobs                 # worker entry wrappers
/ui                     # Next.js admin UI
/infra                  # docker-compose
/tests                  # unit + integration tests
/data
  /fake_drive
  /fake_chorus
/scripts
  generate_fake_drive_docs.py
```

## Stack

- Backend: Python 3.11 + FastAPI
- DB: TiDB Serverless (MySQL wire protocol) or Postgres 16 + pgvector
- Queue/jobs: Celery + Redis
- UI: Next.js 14
- LLM: OpenAI Chat/Embeddings via provider wrapper (deterministic fallback without key)

## Quick start (Docker)

1. Create env file:

```bash
cp .env.example .env
```

2. Start stack:

```bash
cd infra
docker compose up --build
```

Optional: runtime Google service-account secret mount (no secret in image):

```bash
export GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON_FILE=/abs/path/service-account.json
docker compose -f docker-compose.yml -f docker-compose.secrets.yml up --build
```

3. Run initial sync:

```bash
curl -X POST "http://localhost:8000/admin/sync/drive"
curl -X POST "http://localhost:8000/admin/sync/chorus"
```

4. Open:
- API docs: <http://localhost:8000/docs>
- UI: <http://localhost:3000>

Note:
- ChatGPT OAuth callback uses local port `1455` (`http://localhost:1455/auth/callback`), so keep that port available when running in Docker.

## GitHub corpus sync (PingCAP repos/docs)

This project can index local text files under `data/fake_drive/**`.  
Use the helper script to clone/pull GitHub repos into that folder, then run Drive sync.

```bash
export FAKE_DRIVE_INCLUDE_GITHUB=true

python3 scripts/sync_github_sources.py \
  --repo pingcap/tidb:master \
  --repo pingcap/docs:master

curl -X POST "http://localhost:8000/admin/sync/drive"
```

Notes:
- The connector recursively indexes supported text/code files (markdown, rst, txt, yaml/json, go, sql, proto, etc.).
- Files under `data/fake_drive/github/<owner>__<repo>/...` get GitHub source URLs in citations.
- Very large files and binary paths are skipped.

## Local dev (without Docker)

```bash
cd api
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
alembic upgrade head
uvicorn app.main:app --reload
```

## TiDB Serverless database setup

Set `DATABASE_URL` to your TiDB Serverless connection string in `.env` and `api/.env`:

```bash
DATABASE_URL=mysql+pymysql://<user>:<password>@<tidb-host>:4000/<database>?ssl_verify_cert=true&ssl_verify_identity=true
```

Notes:
- If you receive `NXDOMAIN` for a `*-privatelink.*` host, your machine is not on the required VPC/DNS path for that PrivateLink endpoint.
- You can still run locally with SQLite/Postgres; move to TiDB once network routing to the TiDB endpoint is available.

In another shell:

```bash
cd api
celery -A app.worker.celery_app worker --loglevel=info
celery -A app.worker.celery_app beat --loglevel=info
```

## Authentication setup

### LLM + Embeddings provider

Set these env vars in `.env`:

```bash
OPENAI_API_KEY=...
OPENAI_BASE_URL=            # optional; set for OpenAI-compatible providers
OPENAI_MODEL=gpt-4.1-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

Behavior:
- If `OPENAI_API_KEY` is set, chat + embeddings call the configured provider/models.
- If unset, the app falls back to deterministic local hash embeddings and template-based response generation.

### Enterprise security settings (recommended for sensitive customer data)

Set these in `.env` for production:

```bash
ENTERPRISE_MODE=true
SECURITY_REQUIRE_PRIVATE_LLM_ENDPOINT=true
SECURITY_ALLOWED_LLM_BASE_URLS=https://<your-private-llm-gateway>
SECURITY_FAIL_CLOSED_ON_MISSING_LLM_KEY=true
SECURITY_FAIL_CLOSED_ON_MISSING_EMBEDDING_KEY=true
SECURITY_REDACT_BEFORE_LLM=true
SECURITY_REDACT_AUDIT_LOGS=true
SECURITY_TRUSTED_HOST_ALLOWLIST=oracle.pingcap.internal,localhost
SECURITY_ALLOW_INSECURE_HTTP_LLM=false
```

Why this protects data when using external APIs:
- `SECURITY_REQUIRE_PRIVATE_LLM_ENDPOINT` ensures traffic is routed through your approved enterprise gateway instead of accidental public endpoints.
- `SECURITY_ALLOWED_LLM_BASE_URLS` blocks unapproved API hosts (egress allowlist at app layer).
- `SECURITY_FAIL_CLOSED_*` prevents silent fallback behavior, so the app stops instead of sending data through an unintended path.
- `SECURITY_REDACT_BEFORE_LLM` masks emails/phone/card-like strings before prompts/embeddings leave your network.
- `SECURITY_REDACT_AUDIT_LOGS` prevents sensitive fields from being stored in logs.
- `SECURITY_TRUSTED_HOST_ALLOWLIST` reduces host-header abuse by accepting only approved hostnames.

Inspect effective security config at:
- `GET /admin/security/settings`

### Google Drive

Supported modes:

1. Per-user OAuth (recommended for permission inheritance)
- Each signed-in user connects Google Drive in `Settings -> Google Drive Access`.
- TiDB Oracle indexes/searches files using that user’s own Drive permissions (My Drive + Shared Drives).
- Scope: `https://www.googleapis.com/auth/drive.readonly`.
- Tokens are stored encrypted at rest in DB (`google_drive_user_credentials`).
- Set:
  - `GOOGLE_DRIVE_CLIENT_ID`
  - `GOOGLE_DRIVE_CLIENT_SECRET`
  - `GOOGLE_DRIVE_TOKEN_ENCRYPTION_KEY` (required in production; 32-byte key or any string to derive one)

2. Service account (optional legacy mode for shared system sync)
- Set `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=/abs/path/service-account.json`
- For containers, mount that file at runtime (for example into `/run/secrets/service-account.json`) and set `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON` to the mounted path.
- If using Docker Compose, prefer `infra/docker-compose.secrets.yml` and set `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON_FILE`.
- Share target Drive folders/files with the service account.

3. OAuth client token file (legacy local mode)
- Set `GOOGLE_DRIVE_CLIENT_ID` and `GOOGLE_DRIVE_CLIENT_SECRET`
- Store authorized token at path set by `GOOGLE_DRIVE_OAUTH_TOKEN_PATH` (default `.google-drive-token.json`)
- Scope is `drive.readonly`.

### Feishu / Lark

Supported modes:

1. App token mode (shared system sync)
- Set `FEISHU_APP_ID` and `FEISHU_APP_SECRET`.
- In `Admin -> Knowledge Base Configuration`, set one or more Feishu root tokens.
- The Feishu connector recursively traverses configured roots and indexes docs content.

2. Per-user OAuth mode (permission inheritance)
- Enable `feishu_oauth_enabled` in KB config.
- Each signed-in user connects Feishu in `Settings -> Feishu / Lark Access`.
- Sync runs with that user access token; indexed docs are scoped by `user_email` tag for retrieval.
- Tokens are encrypted at rest in DB (`feishu_user_credentials`).

Optional env:
- `FEISHU_OAUTH_SCOPES` (default: `offline_access drive:drive:readonly docs:document:readonly`)
- `FEISHU_OAUTH_STATE_TTL_SECONDS` (default: `600`)

### Chorus

- Set `CHORUS_API_KEY`
- Set `CHORUS_BASE_URL` (e.g., `https://api.chorus.ai/v1`)

### Slack

Direct Slack integration is available through API routes:
- `POST /slack/command` for slash commands
- `POST /slack/events` for Event Subscriptions (`app_mention`)

Required env vars:
- `SLACK_SIGNING_SECRET`
- `SLACK_BOT_TOKEN` (required for `app_mention` responses)

Recommended bot scopes:
- `commands`
- `chat:write`
- `users:read.email` (so TiDB Oracle can map Slack users to Drive-permission-aware email identities)

Command examples:
- `/tidb-oracle How should we position TiDB for Aurora MySQL at 50TB?`
- `/tidb-oracle call_assistant: summarize risks for call_12345`

Without creds, connector uses synthetic fixtures in `data/fake_drive` and `data/fake_chorus`.

## API highlights

### Chat

`POST /chat`

Input:

```json
{
  "mode": "oracle",
  "user": "stephen.thorn@pingcap.com",
  "message": "How should we position TiDB vs SingleStore for a 40-50TB workload?",
  "top_k": 8,
  "filters": {"source_type": ["google_drive", "chorus"], "account": ["Evernorth"]}
}
```

Output includes:
- `answer`
- `citations[]` with `source_id`, `chunk_id`, `quote`, `relevance`
- `follow_up_questions[]`

### Sales Rep Market Research Strategist

`POST /rep/market-research`

Input expects two CSV payloads:
- `current_customers_csv` headers: `account,region,industry,current_platform,use_case,arr`
- `pipeline_csv` headers: `account,region,stage,industry,workload,est_arr,close_quarter,competing_vendor`

Response includes:
- `summary`
- `required_inputs[]`
- `priority_accounts[]`
- `execution_plan[]`

### Draft messaging (internal only)

`POST /messages/draft`

- In `EMAIL_MODE=draft`, responses remain draft even when `mode=send`.
- External recipient attempts are blocked with explicit reason.

### Sync endpoints

- `POST /admin/sync/drive?since=<ISO_TS>`
- `POST /admin/sync/chorus?since=<YYYY-MM-DD>`

### KB CLI

From `api/`:

```bash
kb sync --since 2026-02-17T00:00:00Z
kb search "tiflash sizing" --topk 8
kb inspect <file_id>
```

## Daily ingestion schedule

Celery beat registers `daily_ingestion` every 24h.

## Acceptance test coverage

Implemented in `tests/integration`:

- 50+ doc ingest and search retrieval correctness.
- Chorus incremental sync adds only new calls.
- Per-call artifact generation present.
- External recipient blocked on messaging.
- Chat returns answer + citations + follow-ups.
- Empty retrieval path fails safely.
- Audit logs include query/retrieval/output/timestamp/mode.

Run tests:

```bash
cd api
pip install -e .[dev]
cd ..
pytest -q
```

## Operational runbook

1. Verify infra health:
- `GET /admin/health`
- DB and Redis connectivity in container logs.

2. Run manual sync:
- Drive then Chorus sync endpoints.
- Check `GET /admin/audit` for statuses.

3. Validate chat grounding:
- Submit `POST /chat` and confirm citations map to `chunk_id` and `source_id`.

4. Validate outbound guardrail:
- Test draft with external email; must return `mode=blocked`.

5. Incident handling:
- If retrieval quality drops, inspect `audit_logs.retrieval.results` and rerun sync.
- If messaging fails in send mode, verify SMTP env vars and domain allowlist.
