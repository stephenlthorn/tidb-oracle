# Responses API + Model/Tool Config Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Switch LLMService from Chat Completions to the OpenAI Responses API, add admin-configurable model selection (default `gpt-5.3-codex`) and tool toggles (web search, code interpreter).

**Architecture:** Three new columns on `kb_config` store model + tool preferences. `LLMService` drops `_chat_json`/`chat.completions.create` and replaces it with `_responses_json`/`responses.create`, reading model and tools from the config passed in by `ChatOrchestrator`. The admin panel gains a model button-group and two tool checkboxes.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, OpenAI Python SDK v1.40+, Next.js 14 App Router, React

---

### Task 1: Add columns to KBConfig model + migration

**Files:**
- Modify: `api/app/models/entities.py` (lines 161–175, KBConfig class)
- Modify: `api/app/schemas/kb_config.py`
- Create: `api/alembic/versions/20260225_000001_add_llm_config_to_kb_config.py`

**Step 1: Add 3 columns to KBConfig in entities.py**

Inside the `KBConfig` class, after the `retrieval_top_k` line and before `updated_at`, add:

```python
    llm_model: Mapped[str] = mapped_column(String(100), default="gpt-5.3-codex", nullable=False, server_default="gpt-5.3-codex")
    web_search_enabled: Mapped[bool] = mapped_column(default=False, nullable=False, server_default="false")
    code_interpreter_enabled: Mapped[bool] = mapped_column(default=False, nullable=False, server_default="false")
```

**Step 2: Add fields to KBConfigUpdate schema**

In `api/app/schemas/kb_config.py`, add to `KBConfigUpdate`:
```python
    llm_model: str | None = None
    web_search_enabled: bool | None = None
    code_interpreter_enabled: bool | None = None
```

And to `KBConfigRead`:
```python
    llm_model: str
    web_search_enabled: bool
    code_interpreter_enabled: bool
```

**Step 3: Write Alembic migration**

Create `api/alembic/versions/20260225_000001_add_llm_config_to_kb_config.py`:

```python
"""add llm config to kb_config

Revision ID: 20260225_000001
Revises: 20260224_000002
Create Date: 2026-02-25
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "20260225_000001"
down_revision = "20260224_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("kb_config", sa.Column("llm_model", sa.String(100), nullable=False, server_default="gpt-5.3-codex"))
    op.add_column("kb_config", sa.Column("web_search_enabled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("kb_config", sa.Column("code_interpreter_enabled", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("kb_config", "code_interpreter_enabled")
    op.drop_column("kb_config", "web_search_enabled")
    op.drop_column("kb_config", "llm_model")
```

**Step 4: Apply migration**

```bash
cd "/Users/stephen/Documents/New project/api"
source .venv/bin/activate
alembic upgrade head
```

Expected: `Running upgrade 20260224_000002 -> 20260225_000001`

**Step 5: Verify**

```bash
python -c "
import sys; sys.path.insert(0, '.')
from app.models import KBConfig
cols = [c.key for c in KBConfig.__table__.columns]
assert 'llm_model' in cols
assert 'web_search_enabled' in cols
assert 'code_interpreter_enabled' in cols
print('OK:', cols)
"
```

**Step 6: Commit**

```bash
cd "/Users/stephen/Documents/New project"
git add api/app/models/entities.py api/app/schemas/kb_config.py api/alembic/versions/20260225_000001_add_llm_config_to_kb_config.py
git commit -m "feat: add llm_model + tool flags to KBConfig (Task 1)"
```

---

### Task 2: Switch LLMService to Responses API

**Files:**
- Modify: `api/app/services/llm.py`

The Responses API shape:
```python
response = client.responses.create(
    model="gpt-5.3-codex",
    tools=[{"type": "web_search_preview"}],  # optional
    input=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
    text={"format": {"type": "json_object"}},  # for structured output
)
# Extract text: next item where type=="message"
text = next(
    item.content[0].text
    for item in response.output
    if item.type == "message"
)
```

**Step 1: Replace `_chat_json` with `_responses_json`**

Remove the entire `_chat_json` method and replace with:

```python
    def _responses_json(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        tools: list[dict] | None = None,
    ) -> dict[str, Any] | None:
        if not self.client:
            return None
        import logging
        logger = logging.getLogger(__name__)
        try:
            safe_user_prompt = self._sanitize_for_provider(user_prompt)
            kwargs: dict[str, Any] = {
                "model": model or self.model,
                "input": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": safe_user_prompt},
                ],
                "text": {"format": {"type": "json_object"}},
            }
            if tools:
                kwargs["tools"] = tools
            response = self.client.responses.create(**kwargs)
            payload = next(
                (item.content[0].text for item in response.output if item.type == "message"),
                "{}",
            )
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                return None
        except Exception as exc:
            logger.warning("LLM call failed (%s: %s) — using fallback response", type(exc).__name__, exc)
            return None
```

**Step 2: Update `answer_oracle` signature to accept model and tools**

Change the signature from:
```python
def answer_oracle(self, message: str, hits: list[RetrievedChunk]) -> dict[str, Any]:
```
to:
```python
def answer_oracle(self, message: str, hits: list[RetrievedChunk], *, model: str | None = None, tools: list[dict] | None = None) -> dict[str, Any]:
```

Replace the `self._chat_json(SYSTEM_ORACLE, prompt)` call with:
```python
llm = self._responses_json(SYSTEM_ORACLE, prompt, model=model, tools=tools)
```

**Step 3: Update `answer_call_assistant` signature similarly**

```python
def answer_call_assistant(self, message: str, hits: list[RetrievedChunk], *, model: str | None = None, tools: list[dict] | None = None) -> dict[str, Any]:
```

Replace `self._chat_json(SYSTEM_CALL_COACH, prompt)` with:
```python
llm = self._responses_json(SYSTEM_CALL_COACH, prompt, model=model, tools=tools)
```

**Step 4: Smoke-test the change compiles**

```bash
cd "/Users/stephen/Documents/New project/api"
source .venv/bin/activate
python -c "
import sys; sys.path.insert(0, '.')
from app.services.llm import LLMService
svc = LLMService()  # no key — client will be None
print('LLMService init OK, client:', svc.client)
assert hasattr(svc, '_responses_json'), 'missing _responses_json'
assert not hasattr(svc, '_chat_json'), '_chat_json should be removed'
print('OK')
"
```

**Step 5: Commit**

```bash
cd "/Users/stephen/Documents/New project"
git add api/app/services/llm.py
git commit -m "feat: switch LLMService to Responses API (Task 2)"
```

---

### Task 3: Wire model + tools through ChatOrchestrator

**Files:**
- Modify: `api/app/services/chat_orchestrator.py`

**Step 1: Add `_resolve_llm_config` helper**

After `_resolve_allowed_sources`, add:

```python
    @staticmethod
    def _resolve_llm_config(kb_config: KBConfig | None, settings: "Settings") -> tuple[str, list[dict]]:
        model = (kb_config.llm_model if kb_config else None) or settings.openai_model
        tools: list[dict] = []
        if kb_config:
            if kb_config.web_search_enabled:
                tools.append({"type": "web_search_preview"})
            if kb_config.code_interpreter_enabled:
                tools.append({"type": "code_interpreter", "container": {"type": "auto"}})
        return model, tools
```

**Step 2: Use it in `run`**

In the `run` method, after the existing `allowed_sources = self._resolve_allowed_sources(kb_config)` line, add:

```python
        llm_model, llm_tools = self._resolve_llm_config(kb_config, self.settings)
```

Then update both LLM calls to pass model and tools:

```python
        data = self.llm.answer_call_assistant(message, hits, model=llm_model, tools=llm_tools)
        # and
        data = self.llm.answer_oracle(message, hits, model=llm_model, tools=llm_tools)
```

**Step 3: Verify imports — `Settings` type hint needs to be importable**

Check that `get_settings` is already imported (it is, from `app.core.settings`). The type hint `"Settings"` is a forward reference string so no extra import needed.

**Step 4: Smoke-test**

```bash
cd "/Users/stephen/Documents/New project/api"
source .venv/bin/activate
python -c "
import sys; sys.path.insert(0, '.')
from app.services.chat_orchestrator import ChatOrchestrator
from app.db.session import SessionLocal
db = SessionLocal()
orch = ChatOrchestrator(db, openai_token=None)
print('ChatOrchestrator init OK')
db.close()
"
```

**Step 5: Test with live API call**

```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"mode":"oracle","user":"test@pingcap.com","message":"what is TiDB?","top_k":4}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('answer:', d.get('answer','')[:120])"
```

Expected: JSON answer (may use fallback if no key configured — that's fine).

**Step 6: Commit**

```bash
cd "/Users/stephen/Documents/New project"
git add api/app/services/chat_orchestrator.py
git commit -m "feat: wire llm_model + tools through ChatOrchestrator (Task 3)"
```

---

### Task 4: Admin panel — model selector + tool toggles

**Files:**
- Modify: `ui/components/KBConfigPanel.js`

**Step 1: Add model options constant at top of file (after `'use client'`)**

```javascript
const MODELS = [
  { id: 'gpt-5.3-codex', label: '5.3 Codex' },
  { id: 'gpt-5.2-codex', label: '5.2 Codex' },
  { id: 'gpt-5.1-codex', label: '5.1 Codex' },
  { id: 'gpt-5.1',       label: 'GPT-5.1'   },
  { id: 'gpt-5-codex-mini', label: 'Mini'   },
];
```

**Step 2: Add model selector block**

Inside the returned JSX, add a new section after the retrieval depth block and before the Google Drive block:

```jsx
      {/* Model selector */}
      <div style={{ borderTop: '1px solid var(--border)', paddingTop: '1rem' }}>
        <label style={{ fontSize: '0.8rem', color: 'var(--dim)', display: 'block', marginBottom: '0.5rem' }}>
          LLM MODEL
        </label>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          {MODELS.map(m => (
            <button
              key={m.id}
              className={config.llm_model === m.id ? 'btn btn-primary' : 'btn'}
              style={{ fontSize: '0.75rem' }}
              onClick={() => set('llm_model', m.id)}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tool toggles */}
      <div style={{ borderTop: '1px solid var(--border)', paddingTop: '1rem' }}>
        <label style={{ fontSize: '0.8rem', color: 'var(--dim)', display: 'block', marginBottom: '0.75rem' }}>
          TOOLS
        </label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={!!config.web_search_enabled}
              onChange={e => set('web_search_enabled', e.target.checked)}
            />
            <span style={{ fontSize: '0.82rem' }}>Web Search</span>
            <span style={{ fontSize: '0.75rem', color: 'var(--dim)' }}>— ChatGPT searches the web when relevant</span>
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={!!config.code_interpreter_enabled}
              onChange={e => set('code_interpreter_enabled', e.target.checked)}
            />
            <span style={{ fontSize: '0.82rem' }}>Code Interpreter</span>
            <span style={{ fontSize: '0.75rem', color: 'var(--dim)' }}>— run Python, analyse data</span>
          </label>
        </div>
      </div>
```

**Step 3: Verify file has no syntax errors**

```bash
cd "/Users/stephen/Documents/New project/ui"
node -e "require('fs').readFileSync('components/KBConfigPanel.js','utf8'); console.log('syntax OK')"
```

(This just checks it reads; Next.js handles JSX parsing.)

**Step 4: Commit**

```bash
cd "/Users/stephen/Documents/New project"
git add "ui/components/KBConfigPanel.js"
git commit -m "feat: model selector + tool toggles in admin KB panel (Task 4)"
```

---

### Task 5: Settings page — live model label

**Files:**
- Modify: `ui/app/(app)/settings/page.js`

**Step 1: Fetch live model from KBConfig**

The settings page is a server component. Add a fetch for the live config at the top of `SettingsPage`:

```javascript
  let liveModel = 'gpt-5.3-codex';
  try {
    const cfg = await apiGet('/admin/kb-config');
    if (cfg?.llm_model) liveModel = cfg.llm_model;
  } catch {
    // silently use default
  }
```

Note: `apiGet` is already imported at the top of the file.

**Step 2: Replace the static model label**

Find:
```javascript
{ label: 'Model', value: 'gpt-4.1-mini (via ChatGPT OAuth)' },
```

Replace with:
```javascript
{ label: 'Model', value: `${liveModel} (via ChatGPT OAuth)` },
```

**Step 3: Commit**

```bash
cd "/Users/stephen/Documents/New project"
git add "ui/app/(app)/settings/page.js"
git commit -m "feat: settings page shows live model from KBConfig (Task 5)"
```

---

### Task 6: End-to-end smoke test

**Step 1: Restart the API to pick up all changes**

```bash
# Ctrl+C the running uvicorn, then:
cd "/Users/stephen/Documents/New project/api"
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Step 2: Verify new columns exist**

```bash
python -c "
import sys; sys.path.insert(0, '.')
from app.db.session import engine
from sqlalchemy import text
with engine.connect() as c:
    cols = c.execute(text(\"SELECT column_name FROM information_schema.columns WHERE table_name='kb_config'\")).fetchall()
    names = [r[0] for r in cols]
    assert 'llm_model' in names, f'llm_model missing: {names}'
    assert 'web_search_enabled' in names
    assert 'code_interpreter_enabled' in names
    print('DB columns OK:', names)
"
```

**Step 3: Test API chat endpoint**

```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"mode":"oracle","user":"test@pingcap.com","message":"what is TiDB?","top_k":4}' \
  | python3 -m json.tool | head -10
```

Expected: valid JSON with `answer` key (fallback text if no key set is fine).

**Step 4: Test admin KB config roundtrip**

```bash
# GET
curl -s http://localhost:8000/admin/kb-config | python3 -m json.tool | grep -E "llm_model|web_search|code_inter"

# PUT — set model to gpt-5.2-codex, enable web search
curl -s -X PUT http://localhost:8000/admin/kb-config \
  -H "Content-Type: application/json" \
  -d '{"llm_model":"gpt-5.2-codex","web_search_enabled":true}' \
  | python3 -m json.tool | grep -E "llm_model|web_search"
```

Expected: `llm_model: "gpt-5.2-codex"`, `web_search_enabled: true`

**Step 5: Restore default**

```bash
curl -s -X PUT http://localhost:8000/admin/kb-config \
  -H "Content-Type: application/json" \
  -d '{"llm_model":"gpt-5.3-codex","web_search_enabled":false}' | python3 -m json.tool | grep llm_model
```

**Step 6: Final commit**

```bash
cd "/Users/stephen/Documents/New project"
git add -A
git status  # should be clean
git log --oneline -6
```
