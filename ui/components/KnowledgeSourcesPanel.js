'use client';

import { useEffect, useMemo, useState } from 'react';

const SOURCE_FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'google_drive', label: 'Google Drive' },
  { key: 'feishu', label: 'Feishu' },
  { key: 'chorus', label: 'Chorus' },
];

function sourceLabel(value) {
  if (value === 'all') return 'All';
  if (value === 'google_drive') return 'Google Drive';
  if (value === 'feishu') return 'Feishu';
  if (value === 'chorus') return 'Chorus';
  if (value === 'tidb_docs_online') return 'TiDB Docs';
  return value || 'Unknown';
}

function safeDate(raw) {
  if (!raw) return '-';
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return '-';
  return parsed.toLocaleDateString();
}

export default function KnowledgeSourcesPanel({ docs = [] }) {
  const [query, setQuery] = useState('');
  const [source, setSource] = useState('all');
  const [visible, setVisible] = useState(18);
  const [searchResults, setSearchResults] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState('');

  const normalizedDocs = useMemo(
    () =>
      docs.map((doc, idx) => ({
        id: doc.id || `${doc.source_id || 'doc'}-${idx}`,
        title: doc.title || 'Untitled',
        source_type: doc.source_type || doc.source || 'unknown',
        source_id: doc.source_id || '',
        url: doc.url || '',
        modified_time: doc.modified_time || doc.indexed || null,
      })),
    [docs]
  );

  const sourceCounts = useMemo(() => {
    const counts = { all: normalizedDocs.length };
    for (const doc of normalizedDocs) {
      const key = doc.source_type;
      counts[key] = (counts[key] || 0) + 1;
    }
    return counts;
  }, [normalizedDocs]);

  const docsBySourceId = useMemo(() => {
    const map = new Map();
    for (const doc of normalizedDocs) {
      if (!doc.source_id) continue;
      if (!map.has(doc.source_id)) {
        map.set(doc.source_id, doc);
      }
    }
    return map;
  }, [normalizedDocs]);

  const filteredDocs = useMemo(() => {
    const q = query.trim().toLowerCase();
    return normalizedDocs.filter((doc) => {
      if (source !== 'all' && doc.source_type !== source) return false;
      if (!q) return true;
      const haystack = `${doc.title} ${doc.source_id}`.toLowerCase();
      return haystack.includes(q);
    });
  }, [normalizedDocs, query, source]);

  const hasFullTextQuery = query.trim().length >= 2;

  useEffect(() => {
    if (!hasFullTextQuery) {
      setSearchResults([]);
      setSearchError('');
      setSearchLoading(false);
      return;
    }

    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setSearchLoading(true);
      setSearchError('');
      try {
        const params = new URLSearchParams({
          q: query.trim(),
          limit: '220',
        });
        if (source !== 'all') {
          params.set('source_type', source);
        }

        const res = await fetch(`/api/kb/fulltext?${params.toString()}`, {
          cache: 'no-store',
          signal: controller.signal,
        });
        if (!res.ok) {
          const body = await res.text();
          throw new Error(body || `HTTP ${res.status}`);
        }

        const payload = await res.json();
        const results = Array.isArray(payload?.results) ? payload.results : [];
        const merged = results.map((item, idx) => {
          const sourceDoc = docsBySourceId.get(item.source_id);
          return {
            id: item.chunk_id || `${item.source_id || 'result'}-${idx}`,
            title: item.title || sourceDoc?.title || 'Untitled',
            source_type: item.source_type || sourceDoc?.source_type || 'unknown',
            source_id: item.source_id || sourceDoc?.source_id || '',
            url: item.url || sourceDoc?.url || '',
            modified_time: sourceDoc?.modified_time || null,
            snippet: item.snippet || '',
            score: item.score || 0,
          };
        });
        setSearchResults(merged);
      } catch (err) {
        if (err?.name === 'AbortError') return;
        setSearchResults([]);
        setSearchError('Full-text search failed. Try again in a few seconds.');
      } finally {
        setSearchLoading(false);
      }
    }, 260);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [hasFullTextQuery, query, source, docsBySourceId]);

  const baseRows = hasFullTextQuery ? searchResults : filteredDocs;
  const rows = baseRows.slice(0, visible);
  const canShowMore = baseRows.length > visible;
  const matchCount = hasFullTextQuery ? searchResults.length : filteredDocs.length;

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Knowledge Sources</span>
        <span className="tag">{matchCount} matches</span>
      </div>

      <div className="panel-body">
        <div className="knowledge-toolbar">
          <input
            className="input"
            placeholder="Search full text, title, or file id"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setVisible(18);
            }}
          />
          <div className="status-row">
            {hasFullTextQuery ? 'Full-text mode' : 'Browse mode'} | {sourceLabel(source)} filter
          </div>
          <div className="knowledge-tabs">
            {SOURCE_FILTERS.map((item) => {
              const count = sourceCounts[item.key] || 0;
              const active = source === item.key;
              return (
                <button
                  key={item.key}
                  type="button"
                  className={`btn ${active ? 'btn-primary' : ''}`}
                  onClick={() => {
                    setSource(item.key);
                    setVisible(18);
                  }}
                >
                  {item.label} ({count})
                </button>
              );
            })}
          </div>
        </div>

        {searchLoading && (
          <div className="status-row" style={{ marginTop: '0.5rem' }}>
            Searching full text content...
          </div>
        )}

        {searchError && (
          <div className="error-text" style={{ marginTop: '0.5rem' }}>
            {searchError}
          </div>
        )}

        {rows.length === 0 ? (
          <div className="status-row" style={{ marginTop: '0.5rem' }}>
            {hasFullTextQuery ? 'No full-text matches found.' : 'No documents match this filter.'}
          </div>
        ) : (
          <ul className="knowledge-list">
            {rows.map((doc) => (
              <li key={doc.id} className="knowledge-item">
                <div className="knowledge-main">
                  <div className="knowledge-title">{doc.title}</div>
                  <div className="knowledge-meta">
                    <span>{sourceLabel(doc.source_type)}</span>
                    <span>{doc.source_id || '-'}</span>
                    <span>{safeDate(doc.modified_time)}</span>
                    {hasFullTextQuery ? <span>score {Number(doc.score || 0).toFixed(2)}</span> : null}
                  </div>
                  {hasFullTextQuery && doc.snippet ? <div className="knowledge-snippet">{doc.snippet}</div> : null}
                </div>
                {doc.url ? (
                  <a className="btn" href={doc.url} target="_blank" rel="noreferrer">
                    Open
                  </a>
                ) : (
                  <span className="tag">No URL</span>
                )}
              </li>
            ))}
          </ul>
        )}

        {canShowMore && (
          <div style={{ marginTop: '0.6rem' }}>
            <button type="button" className="btn" onClick={() => setVisible((value) => value + 18)}>
              Show More
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
