import AskOracleWidget from '../../../components/AskOracleWidget';
import MarketResearchWidget from '../../../components/MarketResearchWidget';
import RepExecutionWidget from '../../../components/RepExecutionWidget';

export default function RepPage() {
  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">Sales Rep</div>
          <div className="topbar-meta">Account execution · follow-ups · strategic planning</div>
        </div>
        <div className="topbar-right">
          <span className="tag tag-orange">Execution mode</span>
        </div>
      </div>

      <div className="content">
        <div className="kpi-row">
          {[
            { label: 'Module Set', value: '6', sub: 'Phase 1-3 · Core modules + full orchestration' },
            { label: 'Status', value: 'Live', sub: 'Connected to backend endpoints' },
            { label: 'Persona', value: 'Rep', sub: 'Prompt-aware outputs' },
          ].map((k) => (
            <div className="kpi-card" key={k.label}>
              <div className="kpi-label">{k.label}</div>
              <div className="kpi-value">{k.value}</div>
              <div className="kpi-sub">{k.sub}</div>
            </div>
          ))}
        </div>

        <RepExecutionWidget />
        <MarketResearchWidget />
        <AskOracleWidget defaultQuestion="How should we position TiDB vs SingleStore for a 40TB analytics workload?" />
      </div>
    </>
  );
}
