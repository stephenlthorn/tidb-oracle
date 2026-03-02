'use client';

import { useState } from 'react';

const SAMPLE_ACCOUNTS = ['Evernorth Health', 'Northwind Health', 'Summit Retail'];
const SAMPLE_CALL_IDS = ['', 'call_12345', 'call_67890', 'call_aurora_001_intro', 'call_aurora_002_technical', 'call_aurora_003_poc'];

export default function SEExecutionWidget() {
  const [account, setAccount] = useState(SAMPLE_ACCOUNTS[0]);
  const [chorusCallId, setChorusCallId] = useState('');
  const [targetOffering, setTargetOffering] = useState('TiDB Cloud Dedicated');
  const [competitor, setCompetitor] = useState('SingleStore');

  const [pocPlan, setPocPlan] = useState(null);
  const [readiness, setReadiness] = useState(null);
  const [architecture, setArchitecture] = useState(null);
  const [coach, setCoach] = useState(null);
  const [fullSolution, setFullSolution] = useState(null);

  const [loading, setLoading] = useState('');
  const [error, setError] = useState('');

  const basePayload = { account: account.trim(), chorus_call_id: chorusCallId || null };

  const run = async (kind) => {
    if (!basePayload.account) {
      setError('Enter an account name.');
      return;
    }

    let path = '';
    let payload = { ...basePayload };

    if (kind === 'poc-plan') {
      path = '/api/se/poc-plan';
      payload.target_offering = targetOffering;
    } else if (kind === 'poc-readiness') {
      path = '/api/se/poc-readiness';
    } else if (kind === 'architecture-fit') {
      path = '/api/se/architecture-fit';
    } else if (kind === 'competitor-coach') {
      path = '/api/se/competitor-coach';
      payload.competitor = competitor;
    } else if (kind === 'full') {
      path = '/api/se/full-solution';
      payload.target_offering = targetOffering;
      payload.competitor = competitor;
    }

    setLoading(kind);
    setError('');

    try {
      const res = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || data?.error || 'Request failed');

      if (kind === 'poc-plan') setPocPlan(data);
      if (kind === 'poc-readiness') setReadiness(data);
      if (kind === 'architecture-fit') setArchitecture(data);
      if (kind === 'competitor-coach') setCoach(data);
      if (kind === 'full') {
        setFullSolution(data);
        setPocPlan(data.poc_plan || null);
        setReadiness(data.poc_readiness || null);
        setArchitecture(data.architecture_fit || null);
        setCoach(data.competitor_coach || null);
      }
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setLoading('');
    }
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">SE Automation</span>
        <span className="tag">Phase 1-3</span>
      </div>
      <div className="panel-body" style={{ display: 'grid', gap: '0.75rem' }}>
        <div className="two-col" style={{ gap: '0.75rem' }}>
          <div style={{ display: 'grid', gap: '0.35rem' }}>
            <label style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>Account</label>
            <input className="input" value={account} onChange={(e) => setAccount(e.target.value)} list="se-accounts" />
            <datalist id="se-accounts">
              {SAMPLE_ACCOUNTS.map((a) => <option key={a} value={a} />)}
            </datalist>
          </div>
          <div style={{ display: 'grid', gap: '0.35rem' }}>
            <label style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>Chorus Call (optional)</label>
            <select className="input" value={chorusCallId} onChange={(e) => setChorusCallId(e.target.value)}>
              {SAMPLE_CALL_IDS.map((id) => (
                <option key={id || 'latest'} value={id}>{id || 'Latest for account'}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="two-col" style={{ gap: '0.75rem' }}>
          <div style={{ display: 'grid', gap: '0.35rem' }}>
            <label style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>Target Offering</label>
            <select className="input" value={targetOffering} onChange={(e) => setTargetOffering(e.target.value)}>
              <option>TiDB Cloud Dedicated</option>
              <option>TiDB Self-Managed</option>
              <option>TiDB Enterprise Edition</option>
            </select>
          </div>
          <div style={{ display: 'grid', gap: '0.35rem' }}>
            <label style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>Competitor</label>
            <input className="input" value={competitor} onChange={(e) => setCompetitor(e.target.value)} />
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <button className="btn btn-primary" onClick={() => run('full')} disabled={Boolean(loading)}>
            {loading === 'full' ? 'Generating…' : 'Generate Full Solution (Phases 1-3)'}
          </button>
          <button className="btn btn-primary" onClick={() => run('poc-plan')} disabled={Boolean(loading)}>
            {loading === 'poc-plan' ? 'Generating…' : 'Generate POC Plan'}
          </button>
          <button className="btn" onClick={() => run('poc-readiness')} disabled={Boolean(loading)}>
            {loading === 'poc-readiness' ? 'Generating…' : 'Check Readiness'}
          </button>
          <button className="btn" onClick={() => run('architecture-fit')} disabled={Boolean(loading)}>
            {loading === 'architecture-fit' ? 'Generating…' : 'Architecture Fit'}
          </button>
          <button className="btn" onClick={() => run('competitor-coach')} disabled={Boolean(loading)}>
            {loading === 'competitor-coach' ? 'Generating…' : 'Competitor Coach'}
          </button>
        </div>

        {error ? <div className="error-text">{error}</div> : null}

        {(fullSolution || pocPlan || readiness || architecture || coach) && (
          <div className="answer-box" style={{ display: 'grid', gap: '0.65rem' }}>
            {fullSolution && (
              <div>
                <div className="citation-label">Full Solution Validation Matrix</div>
                <ul className="citation-list">
                  {(fullSolution.phase_2_validation_matrix || []).map((item, idx) => (
                    <li key={`${item.check}-${idx}`}>
                      {item.check}: {item.target} ({item.owner})
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {pocPlan && (
              <div>
                <div className="citation-label">POC Plan ({pocPlan.status}, {pocPlan.readiness_score}/100)</div>
                <div className="answer-text">{pocPlan.readiness_summary}</div>
                {pocPlan.poc_kit_url ? (
                  <div style={{ marginTop: '0.35rem', fontSize: '0.75rem' }}>
                    POC kit: <a href={pocPlan.poc_kit_url} target="_blank" rel="noreferrer">{pocPlan.poc_kit_url}</a>
                  </div>
                ) : null}
              </div>
            )}

            {readiness && (
              <div style={{ borderTop: '1px solid var(--border)', paddingTop: '0.6rem' }}>
                <div className="citation-label">Readiness</div>
                <div className="answer-text">{readiness.readiness_summary}</div>
              </div>
            )}

            {architecture && (
              <div style={{ borderTop: '1px solid var(--border)', paddingTop: '0.6rem' }}>
                <div className="citation-label">Architecture Fit</div>
                <div className="answer-text">{architecture.fit_summary}</div>
              </div>
            )}

            {coach && (
              <div style={{ borderTop: '1px solid var(--border)', paddingTop: '0.6rem' }}>
                <div className="citation-label">Competitor Coach ({coach.competitor})</div>
                <ul className="citation-list">
                  {(coach.positioning || []).slice(0, 4).map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
