# Responses API + Model/Tool Config — Design

**Date:** 2026-02-25
**Status:** Approved

## Goal

Replace the current `chat.completions.create` backend with OpenAI's **Responses API**, enabling:
- Codex models (`gpt-5.3-codex` default)
- Built-in web search (`web_search_preview` tool)
- Code interpreter (`code_interpreter` tool)
- Admin-configurable model and tool toggles

## Approved Approach

**Option A — Full switch to Responses API.** The Responses API is the only path that supports Codex models and built-in tools natively with the ChatGPT OAuth token.

---

## Section 1 — Database

Add 3 columns to the existing `kb_config` table via a new Alembic migration:

| Column | Type | Default |
|---|---|---|
| `llm_model` | `varchar(100)` | `"gpt-5.3-codex"` |
| `web_search_enabled` | `bool` | `false` |
| `code_interpreter_enabled` | `bool` | `false` |

Update `KBConfigRead` and `KBConfigUpdate` Pydantic schemas accordingly.

---

## Section 2 — Backend: LLMService

Replace `client.chat.completions.create` with `client.responses.create`:

- `answer_oracle`: reads `llm_model`, `web_search_enabled`, `code_interpreter_enabled` from KBConfig; builds tools list; calls Responses API; parses output from `response.output` items
- `answer_call_assistant`: same API switch, structured JSON output via `text.format` response format
- Model and tools read from KBConfig at query time (same pattern as `retrieval_top_k`)
- `_chat_json` replaced with `_responses_json` using new API shape
- Error handling (try/except returning `None`) preserved from existing fix

### Model options

| Model ID | Use case |
|---|---|
| `gpt-5.3-codex` | Default — latest Codex, best for code + reasoning |
| `gpt-5.2-codex` | ~40% faster alternative |
| `gpt-5.1-codex` | Previous generation |
| `gpt-5.1` | General purpose (non-code) |
| `gpt-5-codex-mini` | Cheaper, 4x more usage on subscription |

### Tools

- `web_search_preview` — enabled via `web_search_enabled` flag
- `code_interpreter` — enabled via `code_interpreter_enabled` flag

---

## Section 3 — Admin UI

Extend existing `KBConfigPanel` component with two new blocks (save via existing "Save Config" button):

**Model selector** — button group (matching top-k style) with 5 model options, active model highlighted in orange accent.

**Tool toggles** — two checkboxes:
- "Web Search" (off by default) — note: "ChatGPT searches the web when relevant"
- "Code Interpreter" (off by default)

**Settings page** — update static "gpt-4.1-mini" label to read live value from KBConfig via `apiGet`.

---

## Files Changed

| File | Change |
|---|---|
| `api/app/models/entities.py` | Add 3 columns to `KBConfig` |
| `api/alembic/versions/` | New migration |
| `api/app/schemas/kb_config.py` | Add new fields to Read/Update schemas |
| `api/app/services/llm.py` | Switch to Responses API, read model+tools from config |
| `api/app/services/chat_orchestrator.py` | Pass model+tools config to LLMService |
| `ui/components/KBConfigPanel.js` | Model selector + tool toggles |
| `ui/app/(app)/settings/page.js` | Live model label |
