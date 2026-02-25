"""Live TiDB documentation retriever.

Searches docs.pingcap.com via DuckDuckGo Lite (no API key needed) and
fetches the top result pages, returning cleaned text as RetrievedChunk objects.
All errors are swallowed — callers always get a (possibly empty) list.
"""
from __future__ import annotations

import logging
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse
from uuid import uuid4

import httpx

from app.models.entities import SourceType
from app.retrieval.types import RetrievedChunk

logger = logging.getLogger(__name__)

_DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"
_DDG_HTML_URL = "https://duckduckgo.com/html/"
_SEARCH_TIMEOUT = 8.0
_FETCH_TIMEOUT = 6.0
_USER_AGENT = "Mozilla/5.0 (compatible; TiDB-Oracle/1.0; +https://pingcap.com)"
_ONLINE_SCORE = 0.72  # Fixed relevance score for online docs hits.
_DEFAULT_DOC_URLS = [
    "https://docs.pingcap.com/tidb/stable/overview",
    "https://docs.pingcap.com/tidb/stable/tidb-architecture",
    "https://docs.pingcap.com/tidb/stable/mysql-compatibility",
]
_KEYWORD_DOC_URLS = [
    ("aurora", "https://docs.pingcap.com/tidb/stable/migrate-aurora-to-tidb"),
    ("migration", "https://docs.pingcap.com/tidb/stable/migration-overview"),
    ("ddl", "https://docs.pingcap.com/tidb/stable/mysql-compatibility"),
    ("storage", "https://docs.pingcap.com/tidb/stable/tidb-storage"),
    ("architecture", "https://docs.pingcap.com/tidb/stable/tidb-architecture"),
    ("security", "https://docs.pingcap.com/tidb/stable/best-practices-for-security-configuration"),
]


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
    """Return deduplicated docs.pingcap.com URLs found in *html*."""
    parser = _HrefCollector()
    parser.feed(html)
    seen: set[str] = set()
    result: list[str] = []
    for href in parser.hrefs:
        candidate = href
        if "uddg=" in href:
            query = parse_qs(urlparse(href).query)
            if query.get("uddg"):
                candidate = unquote(query["uddg"][0])
        if candidate.startswith("//"):
            candidate = f"https:{candidate}"
        if "docs.pingcap.com" in candidate and candidate not in seen:
            seen.add(candidate)
            result.append(candidate)
    return result


def _extract_text_from_html(html: str, max_chars: int = 2_500) -> str:
    """Return visible article text from *html*, capped at *max_chars*."""
    parser = _TextExtractor()
    parser.feed(html)
    return " ".join(parser.chunks)[:max_chars]


class TiDBDocsRetriever:
    """Deterministically fetch fresh TiDB documentation for a query."""

    @staticmethod
    def _heuristic_docs_urls(query: str) -> list[str]:
        lowered = query.lower()
        urls: list[str] = []
        for keyword, url in _KEYWORD_DOC_URLS:
            if keyword in lowered and url not in urls:
                urls.append(url)
        for url in _DEFAULT_DOC_URLS:
            if url not in urls:
                urls.append(url)
        return urls

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

    def _search_docs_urls(self, query: str) -> list[str]:
        with httpx.Client(timeout=_SEARCH_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(
                _DDG_LITE_URL,
                params={"q": f"site:docs.pingcap.com tidb {query}"},
                headers={"User-Agent": _USER_AGENT},
            )
            urls = _extract_pingcap_urls(resp.text)
            if urls:
                return urls
            # Some regions often get anti-bot 202 pages from the lite endpoint.
            html_resp = client.get(
                _DDG_HTML_URL,
                params={"q": f"site:docs.pingcap.com tidb {query}"},
                headers={"User-Agent": _USER_AGENT},
            )
            urls = _extract_pingcap_urls(html_resp.text)
            if urls:
                return urls
        return self._heuristic_docs_urls(query)

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
            metadata={"source": SourceType.TIDB_DOCS_ONLINE.value, "url": url},
            source_type=SourceType.TIDB_DOCS_ONLINE.value,
            source_id=url,
            title=title,
            url=url,
            file_id=None,
        )
