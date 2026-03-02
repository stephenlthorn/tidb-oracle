import AskOracleWidget from '../../../components/AskOracleWidget';
import SEExecutionWidget from '../../../components/SEExecutionWidget';

export default function SEPage() {
  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">Sales Engineer</div>
          <div className="topbar-meta">POC planning · readiness gates · technical positioning</div>
        </div>
        <div className="topbar-right">
          <span className="tag tag-orange">Execution mode</span>
        </div>
      </div>

      <div className="content">
        <div className="kpi-row">
          {[
            { label: 'Module Set', value: '4', sub: 'POC · Readiness · Fit · Competitor' },
            { label: 'Status', value: 'Live', sub: 'Connected to backend endpoints' },
            { label: 'Persona', value: 'SE', sub: 'Prompt-aware outputs' },
          ].map((k) => (
            <div className="kpi-card" key={k.label}>
              <div className="kpi-label">{k.label}</div>
              <div className="kpi-value">{k.value}</div>
              <div className="kpi-sub">{k.sub}</div>
            </div>
          ))}
        </div>

        <SEExecutionWidget />
        <AskOracleWidget defaultQuestion="What are the TiFlash replication lag characteristics for a 10TB HTAP workload?" />
      </div>
    </>
  );
}
