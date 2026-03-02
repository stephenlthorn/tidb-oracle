'use client';

import { useMemo, useState } from 'react';

const SAMPLE_ACCOUNTS = ['Evernorth Health', 'Northwind Health', 'Summit Retail'];
const SAMPLE_CALL_IDS = ['', 'call_12345', 'call_67890', 'call_aurora_001_intro', 'call_aurora_002_technical', 'call_aurora_003_poc'];

function Section({ title, children }) {
  return (
    <div style={{ borderTop: '1px solid var(--border)', paddingTop: '0.7rem', marginTop: '0.2rem' }}>
      <div className="citation-label" style={{ marginBottom: '0.45rem' }}>{title}</div>
      {children}
    </div>
  );
}

export default function RepExecutionWidget() {
  const [account, setAccount] = useState(SAMPLE_ACCOUNTS[0]);
  const [chorusCallId, setChorusCallId] = useState('');
  const [count, setCount] = useState(6);
  const [tone, setTone] = useState('crisp');
  const [to, setTo] = useState('estyn.c@pingcap.com');
  const [cc, setCc] = useState('se.demo@pingcap.com');
  const [mode, setMode] = useState('draft');

  const [brief, setBrief] = useState(null);
  const [questions, setQuestions] = useState(null);
  const [risk, setRisk] = useState(null);
  const [draft, setDraft] = useState(null);

  const [loadingAction, setLoadingAction] = useState('');
  const [error, setError] = useState('');

  const basePayload = useMemo(
    () => ({ account: account.trim(), chorus_call_id: chorusCallId || null }),
    [account, chorusCallId]
  );

  const run = async (action) => {
    if (!basePayload.account) {
      setError('Enter an account name.');
      return;
    }
    setError('');
    setLoadingAction(action);
    try {
      let path = '';
      let payload = { ...basePayload };

      if (action === 'brief') {
        path = '/api/rep/account-brief';
      } else if (action === 'questions') {
        path = '/api/rep/discovery-questions';
        payload.count = Number(count) || 6;
      } else if (action === 'risk') {
        path = '/api/rep/deal-risk';
      } else if (action === 'draft') {
        path = '/api/rep/follow-up-draft';
        payload.to = to.split(',').map((s) => s.trim()).filter(Boolean);
        payload.cc = cc.split(',').map((s) => s.trim()).filter(Boolean);
        payload.mode = mode;
        payload.tone = tone;
      }

      const res = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.detail || data?.error || 'Request failed');
      }

      if (action === 'brief') setBrief(data);
      if (action === 'questions') setQuestions(data);
      if (action === 'risk') setRisk(data);
      if (action === 'draft') setDraft(data);
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setLoadingAction('');
    }
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Rep Automation</span>
        <span className="tag">Phase 1</span>
      </div>
      <div className="panel-body" style={{ display: 'grid', gap: '0.75rem' }}>
        <div className="two-col" style={{ gap: '0.75rem' }}>
          <div style={{ display: 'grid', gap: '0.35rem' }}>
            <label style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>Account</label>
            <input className="input" value={account} onChange={(e) => setAccount(e.target.value)} list="rep-accounts" />
            <datalist id="rep-accounts">
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

        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <button className="btn" onClick={() => run('brief')} disabled={Boolean(loadingAction)}>
            {loadingAction === 'brief' ? 'Generating…' : 'Generate Account Brief'}
          </button>
          <button className="btn" onClick={() => run('questions')} disabled={Boolean(loadingAction)}>
            {loadingAction === 'questions' ? 'Generating…' : 'Generate Discovery Questions'}
          </button>
          <button className="btn" onClick={() => run('risk')} disabled={Boolean(loadingAction)}>
            {loadingAction === 'risk' ? 'Generating…' : 'Generate Deal Risk'}
          </button>
          <button className="btn btn-primary" onClick={() => run('draft')} disabled={Boolean(loadingAction)}>
            {loadingAction === 'draft' ? 'Generating…' : 'Generate Follow-Up Draft'}
          </button>
        </div>

        <div className="two-col" style={{ gap: '0.75rem' }}>
          <div style={{ display: 'grid', gap: '0.35rem' }}>
            <label style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>Question Count</label>
            <input className="input" type="number" min={3} max={12} value={count} onChange={(e) => setCount(e.target.value)} />
          </div>
          <div style={{ display: 'grid', gap: '0.35rem' }}>
            <label style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>Draft Tone</label>
            <select className="input" value={tone} onChange={(e) => setTone(e.target.value)}>
              <option value="crisp">Crisp</option>
              <option value="executive">Executive</option>
              <option value="technical">Technical</option>
            </select>
          </div>
        </div>

        <div className="two-col" style={{ gap: '0.75rem' }}>
          <div style={{ display: 'grid', gap: '0.35rem' }}>
            <label style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>To (comma-separated)</label>
            <input className="input" value={to} onChange={(e) => setTo(e.target.value)} />
          </div>
          <div style={{ display: 'grid', gap: '0.35rem' }}>
            <label style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>CC (comma-separated)</label>
            <input className="input" value={cc} onChange={(e) => setCc(e.target.value)} />
          </div>
        </div>

        <div style={{ display: 'grid', gap: '0.35rem', maxWidth: '220px' }}>
          <label style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>Draft Mode</label>
          <select className="input" value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="draft">Draft</option>
            <option value="send">Send</option>
          </select>
        </div>

        {error ? <div className="error-text">{error}</div> : null}

        {(brief || questions || risk || draft) && (
          <div className="answer-box" style={{ display: 'grid', gap: '0.6rem' }}>
            {brief && (
              <Section title="Account Brief">
                <div className="answer-text">{brief.summary}</div>
                <ul className="citation-list" style={{ marginTop: '0.45rem' }}>
                  {(brief.next_meeting_agenda || []).map((item) => <li key={item}>{item}</li>)}
                </ul>
              </Section>
            )}

            {questions && (
              <Section title="Discovery Questions">
                <ul className="citation-list">
                  {(questions.questions || []).map((item) => <li key={item}>{item}</li>)}
                </ul>
              </Section>
            )}

            {risk && (
              <Section title={`Deal Risk (${risk.risk_level || 'n/a'})`}>
                <ul className="citation-list">
                  {(risk.risks || []).map((item, idx) => (
                    <li key={`${item.signal}-${idx}`}>{item.signal} — {item.mitigation}</li>
                  ))}
                </ul>
              </Section>
            )}

            {draft && (
              <Section title={`Follow-Up Draft (${draft.mode})`}>
                <div className="answer-text" style={{ fontWeight: 600, marginBottom: '0.35rem' }}>{draft.subject}</div>
                {draft.reason_blocked ? (
                  <div className="error-text" style={{ marginTop: 0 }}>{draft.reason_blocked}</div>
                ) : (
                  <pre style={{ marginTop: '0.25rem' }}>{draft.body}</pre>
                )}
              </Section>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
