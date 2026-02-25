'use client';

import { useState } from 'react';
import AskOracleWidget from '../../../components/AskOracleWidget';

const CAMPAIGNS = [
  { label: 'ABM Target List', desc: 'Build from intent signals + ICP criteria' },
  { label: 'Outbound Email Sequence', desc: '3-touch sequence for financial services ICP' },
  { label: 'LinkedIn Connection Copy', desc: 'Connection request + follow-up message pair' },
  { label: 'Webinar Invite', desc: 'HTAP + real-time analytics webinar invite' },
];

const METRICS = [
  { label: 'Target Accounts', value: '42' },
  { label: 'Open Opportunities', value: '13' },
  { label: 'New Leads (7d)', value: '26' },
  { label: 'Content Assets', value: '8' },
];

export default function MarketingPage() {
  const [log, setLog] = useState([]);

  const launch = (label) => {
    setLog((prev) => [`[${new Date().toLocaleTimeString()}] ${label} — launched`, ...prev].slice(0, 10));
  };

  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">Marketing</div>
          <div className="topbar-meta">ABM · outreach · content generation</div>
        </div>
        <div className="topbar-right">
          <span className="tag tag-orange">Auto-pilot</span>
        </div>
      </div>

      <div className="content">
        <div className="kpi-row">
          {METRICS.map((m) => (
            <div className="kpi-card" key={m.label}>
              <div className="kpi-label">{m.label}</div>
              <div className="kpi-value">{m.value}</div>
            </div>
          ))}
        </div>

        <div className="two-col">
          <div className="panel">
            <div className="panel-header">
              <span className="panel-title">Campaign Actions</span>
            </div>
            <div className="panel-body" style={{ display: 'grid', gap: '0.5rem' }}>
              {CAMPAIGNS.map((c) => (
                <div key={c.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.5rem 0', borderBottom: '1px solid var(--border)' }}>
                  <div>
                    <div className="row-title" style={{ fontSize: '0.8rem' }}>{c.label}</div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-3)', marginTop: '0.15rem' }}>{c.desc}</div>
                  </div>
                  <button className="btn" onClick={() => launch(c.label)} style={{ flexShrink: 0, marginLeft: '0.75rem' }}>
                    Launch
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">
              <span className="panel-title">Automation Log</span>
            </div>
            <div className="panel-body">
              {log.length === 0 ? (
                <div style={{ color: 'var(--text-3)', fontSize: '0.78rem' }}>No campaigns launched yet.</div>
              ) : (
                <ul style={{ listStyle: 'none', display: 'grid', gap: '0.35rem' }}>
                  {log.map((entry, i) => (
                    <li key={i} style={{ fontSize: '0.75rem', color: 'var(--text-2)', fontFamily: 'var(--font)' }}>
                      <span style={{ color: 'var(--success)' }}>✓ </span>{entry}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>

        <AskOracleWidget defaultQuestion="What are the key HTAP messaging points for financial services accounts replacing Redshift?" />
      </div>
    </>
  );
}
