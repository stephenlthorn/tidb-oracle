'use client';

import { useState } from 'react';

export default function MarketingIntelligenceWidget() {
  const [regions, setRegions] = useState('East, Central');
  const [verticals, setVerticals] = useState('Healthcare, Retail, Financial Services');
  const [campaignGoal, setCampaignGoal] = useState(
    'Increase qualified pipeline and improve conversion with technical-proof-led campaigns.'
  );
  const [lookback, setLookback] = useState(60);
  const [loading, setLoading] = useState(false);
  const [loadingFull, setLoadingFull] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState(null);
  const [fullSolution, setFullSolution] = useState(null);

  const run = async () => {
    setLoading(true);
    setError('');
    setData(null);
    setFullSolution(null);
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

  const runFull = async () => {
    setLoadingFull(true);
    setError('');
    setData(null);
    setFullSolution(null);
    try {
      const payload = {
        regions: regions.split(',').map((v) => v.trim()).filter(Boolean),
        verticals: verticals.split(',').map((v) => v.trim()).filter(Boolean),
        lookback_days: Number(lookback) || 60,
        campaign_goal: campaignGoal,
      };
      const res = await fetch('/api/marketing/full-solution', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body?.detail || body?.error || 'Request failed');
      setFullSolution(body);
      setData(body.intelligence || null);
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setLoadingFull(false);
    }
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Marketing Intelligence</span>
        <span className="tag">Phase 1-3</span>
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
          <button className="btn" onClick={runFull} disabled={loadingFull}>
            {loadingFull ? 'Generating…' : 'Generate Full Solution (Phases 1-3)'}
          </button>
        </div>

        <div style={{ display: 'grid', gap: '0.35rem' }}>
          <label style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>Campaign Goal (for full solution)</label>
          <textarea
            className="input"
            rows={2}
            value={campaignGoal}
            onChange={(e) => setCampaignGoal(e.target.value)}
          />
        </div>

        {error ? <div className="error-text">{error}</div> : null}

        {(data || fullSolution) && (
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

            {fullSolution && (
              <>
                <div style={{ borderTop: '1px solid var(--border)', paddingTop: '0.6rem' }}>
                  <div className="citation-label">Phase 2 Campaign Plan</div>
                  <ul className="citation-list">
                    {(fullSolution.phase_2_campaign_plan || []).map((item) => <li key={item}>{item}</li>)}
                  </ul>
                </div>
                <div>
                  <div className="citation-label">Phase 3 Measurement Plan</div>
                  <ul className="citation-list">
                    {(fullSolution.phase_3_measurement_plan || []).map((item) => <li key={item}>{item}</li>)}
                  </ul>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
