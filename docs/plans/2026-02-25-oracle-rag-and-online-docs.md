# Oracle RAG + Live TiDB Docs Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace stale internal-only answers with a hybrid pipeline: Google Drive + Feishu internal RAG + live TiDB docs fetching + LLM synthesis — and remove Chorus call data from Oracle results entirely.

**Architecture:** Oracle mode is restricted to `google_drive` + `feishu` sources only (Chorus is for `call_assistant` exclusively). A new `TiDBDocsRetriever` deterministically fetches fresh content from `docs.pingcap.com` for every oracle query using DuckDuckGo site-search + `httpx`. `web_search_preview` is always-on for oracle so the LLM can go further when internal context is weak. A rewritten system prompt instructs the LLM to synthesise clearly rather than just dump evidence.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, httpx (already installed), stdlib `html.parser`, OpenAI Responses API

---

### Task 1: Make oracle source filtering mode-aware (remove Chorus from Oracle)

**Files:**
- Modify: `api/app/services/chat_orchestrator.py`

**Context:** `_resolve_allowed_sources` currently includes `chorus` when `kb_config.chorus_enabled` is true, regardless of mode. Oracle should never touch call transcripts.

**Step 1: Update `_resolve_allowed_sources` signature and logic**

Find the method `_resolve_allowed_sources` and replace it with:

```python
@staticmethod
def _resolve_allowed_sources(kb_config: "KBConfig | None", mode: str) -> list[str] | None:
    if mode == "oracle":
        if kb_config is None:
            return [SourceType.GOOGLE_DRIVE.value, SourceType.FEISHU.value]
        allowed: list[str] = []
        if kb_config.google_drive_enabled:
            allowed.append(SourceType.GOOGLE_DRIVE.value)
        if kb_config.feishu_enabled:
            allowed.append(SourceType.FEISHU.value)
        return allowed or [SourceType.GOOGLE_DRIVE.value]
    # call_assistant and any other modes: use Chorus only
    if kb_config is None:
        return None
    allowed = []
    if kb_config.chorus_enabled:
        allowed.append(SourceType.CHORUS.value)
    return allowed or None
```

**Step 2: Update the call site in `run()`**

Find:
```python
allowed_sources = self._resolve_allowed_sources(kb_config)
```

Replace with:
```python
allowed_sources = self._resolve_allowed_sources(kb_config, request.mode)
```

**Step 3: Smoke-test the change compiles**

```bash
cd "/Users/stephen/Documents/New project/api" && source .venv/bin/activate && python -c "
import sys; sys.path.insert(0, '.')
from app.services.chat_orchestrator import ChatOrchestrator
from app.db.session import SessionLocal
db = SessionLocal()
orch = ChatOrchestrator(db, openai_token=None)
print('ChatOrchestrator init OK')
db.close()
"
```

Expected: no import errors.

**Step 4: Quick behavioural test inline**

```bash
cd "/Users/stephen/Documents/New project/api" && source .venv/bin/activate && python -c "
import sys; sys.path.insert(0, '.')
from app.services.chat_orchestrator import ChatOrchestrator
from app.models.entities import KBConfig, SourceType

# Oracle with all sources enabled
cfg = KBConfig(google_drive_enabled=True, feishu_enabled=True, chorus_enabled=True)
result = ChatOrchestrator._resolve_allowed_sources(cfg, 'oracle')
assert 'chorus' not in result, f'chorus leaked into oracle: {result}'
assert 'google_drive' in result, f'google_drive missing: {result}'
print('oracle sources OK:', result)

# Call assistant
result2 = ChatOrchestrator._resolve_allowed_sources(cfg, 'call_assistant')
assert 'chorus' in result2, f'chorus missing from call: {result2}'
assert 'google_drive' not in result2, f'drive leaked into call: {result2}'
print('call sources OK:', result2)

print('ALL PASS')
"
```

**Step 5: Commit**

```bash
cd "/Users/stephen/Documents/New project"
git add api/app/services/chat_orchestrator.py
git commit -m "feat: mode-aware source filtering — oracle never sees Chorus (Task 1)"
```

---

### Task 2: Add TIDB_DOCS_ONLINE SourceType

**Files:**
- Modify: `api/app/models/entities.py`

**Context:** `SourceType` is a plain Python enum (not a DB-level enum constraint), so adding a value is safe without a migration.

**Step 1: Add the new value**

Find:
```python
class SourceType(str, enum.Enum):
    GOOGLE_DRIVE = "google_drive"
    FEISHU = "feishu"
    CHORUS = "chorus"
```

Replace with:
```python
class SourceType(str, enum.Enum):
    GOOGLE_DRIVE = "google_drive"
    FEISHU = "feishu"
    CHORUS = "chorus"
    TIDB_DOCS_ONLINE = "tidb_docs_online"
```

**Step 2: Verify**

```bash
cd "/Users/stephen/Documents/New project/api" && source .venv/bin/activate && python -c "
import sys; sys.path.insert(0, '.')
from app.models.entities import SourceType
assert SourceType.TIDB_DOCS_ONLINE.value == 'tidb_docs_online'
print('OK:', list(SourceType))
"
```

**Step 3: Commit**

```bash
cd "/Users/stephen/Documents/New project"
git add api/app/models/entities.py
git commit -m "feat: add TIDB_DOCS_ONLINE SourceType (Task 2)"
```

---

### Task 3: Build TiDBDocsRetriever

**Files:**
- Create: `api/app/retrieval/tidb_docs.py`
- Create: `api/tests/retrieval/test_tidb_docs.py`

**Context:** Uses `httpx` (already in deps) + stdlib `html.parser`. Searches DuckDuckGo Lite for `site:docs.pingcap.com tidb {query}`, fetches top 3 result pages, extracts visible text, returns as `RetrievedChunk` objects. All errors are swallowed — the caller always gets a (possibly empty) list.

**Step 1: Write the failing test first**

Create `api/tests/retrieval/test_tidb_docs.py`:

```python
"""Tests for TiDBDocsRetriever — exercises the HTML parser and fallback."""
from unittest.mock import patch, MagicMock
import pytest

from app.retrieval.tidb_docs import TiDBDocsRetriever, _extract_text_from_html, _extract_pingcap_urls


# ---------------------------------------------------------------------------
# Unit tests (no network)
# ---------------------------------------------------------------------------

SAMPLE_DDG_HTML = """
<html><body>
  <div class="results">
    <div class="result">
      <a href="https://docs.pingcap.com/tidb/stable/tidb-architecture" class="result__a">TiDB Architecture</a>
      <a href="https://docs.pingcap.com/tidb/stable/overview">Overview</a>
      <a href="https://example.com/not-pingcap">Other</a>
    </div>
  </div>
</body></html>
"""

SAMPLE_DOC_HTML = """
<html><body>
  <main>
    <h1>TiDB Architecture</h1>
    <p>TiDB is a distributed SQL database.</p>
    <p>It supports HTAP workloads.</p>
    <ul><li>Horizontal scalability</li><li>MySQL compatibility</li></ul>
  </main>
</body></html>
"""


def test_extract_pingcap_urls_only_returns_docs_pingcap_links():
    urls = _extract_pingcap_urls(SAMPLE_DDG_HTML)
    assert all("docs.pingcap.com" in u for u in urls)
    assert "example.com" not in str(urls)


def test_extract_pingcap_urls_deduplicates():
    html = SAMPLE_DDG_HTML + SAMPLE_DDG_HTML  # doubled
    urls = _extract_pingcap_urls(html)
    assert len(urls) == len(set(urls))


def test_extract_text_from_html_returns_article_text():
    text = _extract_text_from_html(SAMPLE_DOC_HTML)
    assert "TiDB is a distributed SQL database" in text
    assert "Horizontal scalability" in text


def test_extract_text_from_html_empty_on_garbage():
    text = _extract_text_from_html("<html></html>")
    assert text == "" or len(text) < 10


def test_search_returns_empty_list_on_network_error():
    retriever = TiDBDocsRetriever()
    with patch("app.retrieval.tidb_docs.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.side_effect = Exception("network error")
        result = retriever.search("TiDB storage engine")
    assert result == []


def test_search_returns_chunks_on_success():
    retriever = TiDBDocsRetriever()

    def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "duckduckgo" in url:
            resp.text = SAMPLE_DDG_HTML
        else:
            resp.text = SAMPLE_DOC_HTML
        return resp

    with patch("app.retrieval.tidb_docs.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = fake_get

        chunks = retriever.search("TiDB architecture", max_results=2)

    assert len(chunks) > 0
    chunk = chunks[0]
    assert chunk.source_type == "tidb_docs_online"
    assert chunk.url is not None
    assert "docs.pingcap.com" in chunk.url
    assert len(chunk.text) > 10


def test_search_skips_pages_that_return_non_200():
    retriever = TiDBDocsRetriever()

    def fake_get(url, **kwargs):
        resp = MagicMock()
        if "duckduckgo" in url:
            resp.status_code = 200
            resp.text = SAMPLE_DDG_HTML
        else:
            resp.status_code = 404
            resp.text = ""
        return resp

    with patch("app.retrieval.tidb_docs.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = fake_get

        chunks = retriever.search("TiDB", max_results=2)

    assert chunks == []


def test_search_caps_at_max_results():
    retriever = TiDBDocsRetriever()

    # DDG returns 5 URLs, but we request max_results=2
    many_urls_html = "\n".join([
        f'<a href="https://docs.pingcap.com/tidb/stable/page-{i}">page {i}</a>'
        for i in range(5)
    ])

    def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.text = many_urls_html if "duckduckgo" in url else SAMPLE_DOC_HTML
        return resp

    with patch("app.retrieval.tidb_docs.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = fake_get

        chunks = retriever.search("TiDB", max_results=2)

    assert len(chunks) <= 2
```

**Step 2: Run tests to confirm they fail**

```bash
cd "/Users/stephen/Documents/New project/api" && source .venv/bin/activate && pytest tests/retrieval/test_tidb_docs.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'app.retrieval.tidb_docs'`

**Step 3: Create the implementation**

Create `api/app/retrieval/tidb_docs.py`:

```python
"""Live TiDB documentation retriever.

Searches docs.pingcap.com via DuckDuckGo Lite (no API key needed) and
fetches the top result pages, returning cleaned text as RetrievedChunk objects.
All errors are swallowed — callers always get a (possibly empty) list.
"""
from __future__ import annotations

import logging
from html.parser import HTMLParser
from uuid import uuid4

import httpx

from app.models.entities import SourceType
from app.retrieval.types import RetrievedChunk

logger = logging.getLogger(__name__)

_DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"
_SEARCH_TIMEOUT = 8.0
_FETCH_TIMEOUT = 6.0
_USER_AGENT = "Mozilla/5.0 (compatible; TiDB-Oracle/1.0; +https://pingcap.com)"
_ONLINE_SCORE = 0.72  # fixed relevance score for online docs hits


# ---------------------------------------------------------------------------
# HTML helpers (stdlib only — no beautifulsoup4 needed)
# ---------------------------------------------------------------------------


class _HrefCollector(HTMLParser):
    """Collect all href attribute values from an HTML document."""

    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.hrefs.append(value)


class _TextExtractor(HTMLParser):
    """Extract human-readable text from HTML, skipping script/style blocks."""

    _BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "li", "td", "th", "dt", "dd", "blockquote"}
    _SKIP_TAGS = {"script", "style", "nav", "footer", "header"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._in_block = False
        self.chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        if tag in self._BLOCK_TAGS:
            self._in_block = True

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag in self._BLOCK_TAGS:
            self._in_block = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self._in_block:
            stripped = data.strip()
            if stripped:
                self.chunks.append(stripped)


def _extract_pingcap_urls(html: str) -> list[str]:
    """Return deduped docs.pingcap.com URLs found in *html*."""
    parser = _HrefCollector()
    parser.feed(html)
    seen: set[str] = set()
    result: list[str] = []
    for href in parser.hrefs:
        if "docs.pingcap.com" in href and href not in seen:
            seen.add(href)
            result.append(href)
    return result


def _extract_text_from_html(html: str, max_chars: int = 2_500) -> str:
    """Return visible article text from *html*, capped at *max_chars*."""
    parser = _TextExtractor()
    parser.feed(html)
    return " ".join(parser.chunks)[:max_chars]


# ---------------------------------------------------------------------------
# Public retriever
# ---------------------------------------------------------------------------


class TiDBDocsRetriever:
    """Deterministically fetch fresh TiDB documentation for a query.

    Uses DuckDuckGo Lite to find relevant docs.pingcap.com pages, then
    fetches and parses each page. No API key required.
    """

    def search(self, query: str, max_results: int = 3) -> list[RetrievedChunk]:
        """Return up to *max_results* RetrievedChunks from live TiDB docs.

        Never raises — returns empty list on any failure.
        """
        try:
            urls = self._search_docs_urls(query)
            chunks: list[RetrievedChunk] = []
            for url in urls[:max_results]:
                try:
                    chunk = self._fetch_page(url)
                    if chunk is not None:
                        chunks.append(chunk)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("TiDBDocsRetriever: skipping %s (%s)", url, exc)
            return chunks
        except Exception as exc:  # noqa: BLE001
            logger.warning("TiDBDocsRetriever.search failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _search_docs_urls(self, query: str) -> list[str]:
        with httpx.Client(timeout=_SEARCH_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(
                _DDG_LITE_URL,
                params={"q": f"site:docs.pingcap.com tidb {query}"},
                headers={"User-Agent": _USER_AGENT},
            )
        return _extract_pingcap_urls(resp.text)

    def _fetch_page(self, url: str) -> RetrievedChunk | None:
        with httpx.Client(timeout=_FETCH_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": _USER_AGENT})
        if resp.status_code != 200:
            return None
        text = _extract_text_from_html(resp.text)
        if len(text) < 80:
            return None
        slug = url.rstrip("/").split("/")[-1]
        title = slug.replace("-", " ").title() if slug else "TiDB Docs"
        return RetrievedChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            score=_ONLINE_SCORE,
            text=text,
            metadata={"source": "tidb_docs_online", "url": url},
            source_type=SourceType.TIDB_DOCS_ONLINE.value,
            source_id=url,
            title=title,
            url=url,
            file_id=None,
        )
```

**Step 4: Run tests — all must pass**

```bash
cd "/Users/stephen/Documents/New project/api" && source .venv/bin/activate && pytest tests/retrieval/test_tidb_docs.py -v
```

Expected: all 7 tests PASS.

**Step 5: Commit**

```bash
cd "/Users/stephen/Documents/New project"
git add api/app/retrieval/tidb_docs.py api/tests/retrieval/test_tidb_docs.py
git commit -m "feat: TiDBDocsRetriever — live docs.pingcap.com fetching (Task 3)"
```

---

### Task 4: Wire TiDBDocsRetriever into ChatOrchestrator

**Files:**
- Modify: `api/app/services/chat_orchestrator.py`

**Context:** Oracle mode should always append fresh TiDB docs chunks to the vector-retrieval hits before passing context to the LLM. Call-assistant mode is unchanged.

**Step 1: Add import at top of file**

Find the existing imports at the top of `chat_orchestrator.py`. Add:

```python
from app.retrieval.tidb_docs import TiDBDocsRetriever
```

**Step 2: Instantiate in `__init__`**

Find the `__init__` method. After instantiating `self.retriever` (HybridRetriever), add:

```python
        self.docs_retriever = TiDBDocsRetriever()
```

**Step 3: Call it in `run()` for oracle mode**

Find the `run()` method. After the line:
```python
hits = self.retriever.search(...)
```

Add:
```python
        if request.mode == "oracle":
            online_hits = self.docs_retriever.search(rewritten_query, max_results=3)
            hits = hits + online_hits
```

**Step 4: Smoke-test**

```bash
cd "/Users/stephen/Documents/New project/api" && source .venv/bin/activate && python -c "
import sys; sys.path.insert(0, '.')
from app.services.chat_orchestrator import ChatOrchestrator
from app.db.session import SessionLocal
db = SessionLocal()
orch = ChatOrchestrator(db, openai_token=None)
assert hasattr(orch, 'docs_retriever'), 'docs_retriever not found'
print('ChatOrchestrator + TiDBDocsRetriever: OK')
db.close()
"
```

**Step 5: Commit**

```bash
cd "/Users/stephen/Documents/New project"
git add api/app/services/chat_orchestrator.py
git commit -m "feat: wire TiDBDocsRetriever into oracle ChatOrchestrator (Task 4)"
```

---

### Task 5: Always-on web search for oracle + update `_resolve_llm_config`

**Files:**
- Modify: `api/app/services/chat_orchestrator.py`

**Context:** Oracle mode should always get `web_search_preview` so the LLM can go beyond the pre-fetched docs when needed. The admin `web_search_enabled` toggle is preserved for non-oracle modes. Update `_resolve_llm_config` to accept `mode`.

**Step 1: Update `_resolve_llm_config` signature and logic**

Find `_resolve_llm_config` and replace it with:

```python
    @staticmethod
    def _resolve_llm_config(
        kb_config: "KBConfig | None",
        settings: "Settings",
        mode: str,
    ) -> tuple[str, list[dict]]:
        model = (kb_config.llm_model if kb_config else None) or settings.openai_model
        tools: list[dict] = []
        if mode == "oracle":
            # Always enable web search for oracle — LLM fetches TiDB docs when needed
            tools.append({"type": "web_search_preview"})
        elif kb_config and kb_config.web_search_enabled:
            tools.append({"type": "web_search_preview"})
        if kb_config and kb_config.code_interpreter_enabled:
            tools.append({"type": "code_interpreter", "container": {"type": "auto"}})
        return model, tools
```

**Step 2: Update the call site in `run()`**

Find:
```python
llm_model, llm_tools = self._resolve_llm_config(kb_config, self.settings)
```

Replace with:
```python
llm_model, llm_tools = self._resolve_llm_config(kb_config, self.settings, request.mode)
```

**Step 3: Verify inline**

```bash
cd "/Users/stephen/Documents/New project/api" && source .venv/bin/activate && python -c "
import sys; sys.path.insert(0, '.')
from app.services.chat_orchestrator import ChatOrchestrator
from app.models.entities import KBConfig
from app.core.settings import get_settings

settings = get_settings()

# Oracle mode — web search must ALWAYS be in tools
cfg = KBConfig(web_search_enabled=False)
model, tools = ChatOrchestrator._resolve_llm_config(cfg, settings, 'oracle')
tool_types = [t['type'] for t in tools]
assert 'web_search_preview' in tool_types, f'web_search missing from oracle: {tool_types}'
print('oracle tools OK:', tool_types)

# Call mode with web_search disabled — no web search
cfg2 = KBConfig(web_search_enabled=False)
model2, tools2 = ChatOrchestrator._resolve_llm_config(cfg2, settings, 'call_assistant')
tool_types2 = [t['type'] for t in tools2]
assert 'web_search_preview' not in tool_types2, f'web_search leaked into call: {tool_types2}'
print('call tools OK:', tool_types2)

print('ALL PASS')
"
```

**Step 4: Commit**

```bash
cd "/Users/stephen/Documents/New project"
git add api/app/services/chat_orchestrator.py
git commit -m "feat: always-on web search for oracle mode (Task 5)"
```

---

### Task 6: Rewrite oracle system prompt for synthesis quality

**Files:**
- Modify: `api/app/prompts/templates.py`

**Context:** The current prompt says "answers must be grounded in supplied evidence only" which blocks the LLM from using its web search tool and forces it to dump chunks. Replace with a synthesis-first prompt that uses all available sources.

**Step 1: Replace `SYSTEM_ORACLE`**

Find `SYSTEM_ORACLE` and replace the entire string:

```python
SYSTEM_ORACLE = """
You are PingCAP's internal TiDB + GTM oracle — a technical expert combining internal company knowledge with live TiDB official documentation.

You have access to three types of context (provided in the user message):
1. Internal documents — Google Drive and Feishu files (company-specific positioning, decks, internal guides)
2. Live TiDB docs — freshly fetched from docs.pingcap.com (authoritative product facts, SQL syntax, configuration)
3. Web search — use the web_search tool for anything not covered above

How to answer:
- Synthesise a clear, direct, useful answer — do not just list evidence chunks
- For product facts (features, SQL syntax, limits, configuration): prefer TiDB official docs
- For PingCAP-specific context (deals, positioning, internal processes): prefer Drive/Feishu sources
- If internal context and official docs conflict, prefer official docs and note the discrepancy
- Cite your sources inline: use document title + chunk id for internal docs, URL for online sources
- If you need more current information than provided, use the web_search tool
- If evidence is genuinely insufficient, say so clearly and suggest what to search for

Never suggest outbound messages to non-@pingcap.com recipients.
"""
```

**Step 2: Verify the file is valid Python**

```bash
cd "/Users/stephen/Documents/New project/api" && source .venv/bin/activate && python -c "
import sys; sys.path.insert(0, '.')
from app.prompts.templates import SYSTEM_ORACLE, SYSTEM_CALL_COACH
assert 'Synthesise' in SYSTEM_ORACLE
assert 'web_search' in SYSTEM_ORACLE
assert 'SYSTEM_CALL_COACH' or SYSTEM_CALL_COACH  # just check it exists
print('Prompts OK, SYSTEM_ORACLE length:', len(SYSTEM_ORACLE))
"
```

**Step 3: Commit**

```bash
cd "/Users/stephen/Documents/New project"
git add api/app/prompts/templates.py
git commit -m "feat: rewrite oracle system prompt for synthesis + web search (Task 6)"
```

---

### Task 7: Remove raw-chunk fallback from `answer_oracle`

**Files:**
- Modify: `api/app/services/llm.py`

**Context:** The current fallback when the LLM call fails dumps raw chunks as a bullet list, which is "the internal DB answer". Replace with a structured error response that tells the user what's wrong.

**Step 1: Find the fallback in `answer_oracle`**

Read `api/app/services/llm.py` and find `answer_oracle`. There are two places to update:

1. The `if not hits` early return
2. The `if llm is None` fallback (when LLM call returns None)

**Step 2: Replace both fallbacks**

Replace the `if not hits` block with:
```python
        if not hits:
            return {
                "answer": (
                    "I don't have enough context to answer this question. "
                    "Make sure Google Drive and Feishu are synced in Admin settings. "
                    "You can also try rephrasing your question."
                ),
                "citations": [],
                "follow_up_questions": [
                    "Is Google Drive synced? (Admin → Sync Google Drive)",
                    "Is Feishu configured with a folder token?",
                ],
            }
```

Replace the `if llm is None` / raw chunk dump block with:
```python
        if llm is None:
            return {
                "answer": (
                    "The AI model could not generate a response. "
                    "Please check that your ChatGPT OAuth session is active (Settings → ChatGPT Account) "
                    "or configure an OpenAI API key."
                ),
                "citations": [],
                "follow_up_questions": [],
            }
```

**Step 3: Verify**

```bash
cd "/Users/stephen/Documents/New project/api" && source .venv/bin/activate && python -c "
import sys; sys.path.insert(0, '.')
from app.services.llm import LLMService
svc = LLMService()
# Test no-hits fallback
result = svc.answer_oracle('what is TiDB?', hits=[])
assert 'answer' in result
assert 'citations' in result
assert 'follow_up_questions' in result
# Make sure it does NOT contain a bullet-list dump
assert '•' not in result['answer'] and '- [' not in result['answer']
print('no-hits fallback OK:', result['answer'][:80])
"
```

**Step 4: Commit**

```bash
cd "/Users/stephen/Documents/New project"
git add api/app/services/llm.py
git commit -m "feat: replace raw chunk fallback with helpful error messages (Task 7)"
```

---

### Task 8: End-to-end smoke test

**Step 1: Restart API**

```bash
pkill -f "uvicorn app.main:app" 2>/dev/null; sleep 1
cd "/Users/stephen/Documents/New project/api" && source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
sleep 3
```

**Step 2: Test oracle returns no Chorus sources**

```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"mode":"oracle","user":"test@pingcap.com","message":"what is TiDB?","top_k":4}' \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
cits = d.get('citations', [])
chorus_cits = [c for c in cits if c.get('source_type') == 'chorus']
assert not chorus_cits, f'Chorus leaked into oracle: {chorus_cits}'
print('No Chorus in oracle: OK')
print('Answer preview:', d.get('answer','')[:200])
"
```

**Step 3: Test TiDB docs source appears in citations**

```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"mode":"oracle","user":"test@pingcap.com","message":"TiDB storage engine architecture","top_k":4}' \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
cits = d.get('citations', [])
online_cits = [c for c in cits if c.get('source_type') == 'tidb_docs_online']
print(f'Online docs citations: {len(online_cits)}')
for c in online_cits[:2]:
    print(' -', c.get('title'), c.get('url'))
print('Answer:', d.get('answer','')[:300])
"
```

Expected: ≥1 `tidb_docs_online` citation with a `docs.pingcap.com` URL.

**Step 4: Test admin KB config roundtrip still works**

```bash
curl -s http://localhost:8000/admin/kb-config | python3 -m json.tool | grep -E "llm_model|google_drive|feishu|chorus"
```

**Step 5: Final git log**

```bash
cd "/Users/stephen/Documents/New project" && git log --oneline -8
```

Expected: 7 clean commits from Tasks 1–7 + any pre-existing commits.

---
