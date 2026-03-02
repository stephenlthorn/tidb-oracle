'use client';

import AskOracleWidget from '../../../components/AskOracleWidget';
import MarketingIntelligenceWidget from '../../../components/MarketingIntelligenceWidget';

export default function MarketingPage() {
  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">Marketing</div>
          <div className="topbar-meta">Signal synthesis · campaign angle generation · GTM priorities</div>
        </div>
        <div className="topbar-right">
          <span className="tag tag-orange">Execution mode</span>
        </div>
      </div>

      <div className="content">
        <div className="kpi-row">
          {[
            { label: 'Module Set', value: '2', sub: 'Phase 1-3 · Intelligence + campaign orchestration' },
            { label: 'Status', value: 'Live', sub: 'Connected to backend endpoint' },
            { label: 'Persona', value: 'Marketing', sub: 'Prompt-aware outputs' },
          ].map((m) => (
            <div className="kpi-card" key={m.label}>
              <div className="kpi-label">{m.label}</div>
              <div className="kpi-value">{m.value}</div>
              <div className="kpi-sub">{m.sub}</div>
            </div>
          ))}
        </div>

        <MarketingIntelligenceWidget />
        <AskOracleWidget defaultQuestion="What are the key HTAP messaging points for financial services accounts replacing Redshift?" />
      </div>
    </>
  );
}
