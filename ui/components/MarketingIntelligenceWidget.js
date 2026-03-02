'use client';

import { useState } from 'react';

export default function MarketingIntelligenceWidget() {
  const [regions, setRegions] = useState('East, Central');
  const [verticals, setVerticals] = useState('Healthcare, Retail, Financial Services');
  const [lookback, setLookback] = useState(60);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState(null);

  const run = async () => {
    setLoading(true);
    setError('');
    setData(null);
    try {
      const payload = {
        regions: regions.split(',').map((v) => v.trim()).filter(Boolean),
        verticals: verticals.split(',').map((v) => v.trim()).filter(Boolean),
        lookback_days: Number(lookback) || 60,
      };
      const res = await fetch('/api/marketing/intelligence', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body?.detail || body?.error || 'Request failed');
      setData(body);
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Marketing Intelligence</span>
        <span className="tag">Phase 1</span>
      </div>
      <div className="panel-body" style={{ display: 'grid', gap: '0.75rem' }}>
        <div className="two-col" style={{ gap: '0.75rem' }}>
          <div style={{ display: 'grid', gap: '0.35rem' }}>
            <label style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>Regions</label>
            <input className="input" value={regions} onChange={(e) => setRegions(e.target.value)} />
          </div>
          <div style={{ display: 'grid', gap: '0.35rem' }}>
            <label style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>Verticals</label>
            <input className="input" value={verticals} onChange={(e) => setVerticals(e.target.value)} />
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <label style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>Lookback Days</label>
          <input
            className="input"
            type="number"
            min={14}
            max={365}
            value={lookback}
            onChange={(e) => setLookback(e.target.value)}
            style={{ maxWidth: '120px' }}
          />
          <button className="btn btn-primary" onClick={run} disabled={loading}>
            {loading ? 'Generating…' : 'Generate Intelligence'}
          </button>
        </div>

        {error ? <div className="error-text">{error}</div> : null}

        {data && (
          <div className="answer-box" style={{ display: 'grid', gap: '0.6rem' }}>
            <div className="answer-text">{data.summary}</div>
            <div>
              <div className="citation-label">Top Signals</div>
              <ul className="citation-list">
                {(data.top_signals || []).map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>
            <div>
              <div className="citation-label">Campaign Angles</div>
              <ul className="citation-list">
                {(data.campaign_angles || []).map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
