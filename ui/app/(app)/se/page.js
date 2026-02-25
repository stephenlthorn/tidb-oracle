import { FAKE_CALLS } from '../../../data/fake-calls';
import AskOracleWidget from '../../../components/AskOracleWidget';

const TRACKS = [
  { label: 'TiDB X Assets', desc: 'Benchmark worksheet + architecture one-pager' },
  { label: 'TiDB Cloud Dedicated', desc: 'Deployment checklist + security FAQ pack' },
  { label: 'HTAP Architecture', desc: 'TiKV + TiFlash phased rollout guide' },
  { label: 'POC Scorecard', desc: 'Success criteria template + measurement rubric' },
];

export default function SEPage() {
  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">Sales Engineer</div>
          <div className="topbar-meta">Technical assets · POC planning · architecture guidance</div>
        </div>
        <div className="topbar-right">
          <span className="tag tag-orange">3 active POCs</span>
        </div>
      </div>

      <div className="content">
        <div className="kpi-row">
          {[
            { label: 'Active POCs', value: '3', sub: 'Evernorth · Northwind · Summit' },
            { label: 'Assets Generated', value: '12', sub: 'This month' },
            { label: 'Avg POC Duration', value: '18d', sub: 'vs 24d last quarter' },
          ].map((k) => (
            <div className="kpi-card" key={k.label}>
              <div className="kpi-label">{k.label}</div>
              <div className="kpi-value">{k.value}</div>
              <div className="kpi-sub">{k.sub}</div>
            </div>
          ))}
        </div>

        <div className="two-col">
          <div className="panel">
            <div className="panel-header">
              <span className="panel-title">Asset Generator</span>
              <span className="tag">4 tracks</span>
            </div>
            <div className="panel-body" style={{ display: 'grid', gap: '0.5rem' }}>
              {TRACKS.map((t) => (
                <div key={t.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.5rem 0', borderBottom: '1px solid var(--border)' }}>
                  <div>
                    <div className="row-title" style={{ fontSize: '0.8rem' }}>{t.label}</div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-3)', marginTop: '0.15rem' }}>{t.desc}</div>
                  </div>
                  <button className="btn" style={{ flexShrink: 0, marginLeft: '0.75rem' }}>Generate</button>
                </div>
              ))}
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">
              <span className="panel-title">POC Status</span>
            </div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Stage</th>
                  <th>Key Risk</th>
                </tr>
              </thead>
              <tbody>
                {FAKE_CALLS.map((c) => (
                  <tr key={c.id}>
                    <td className="row-title">{c.account}</td>
                    <td>{c.stage}</td>
                    <td style={{ fontSize: '0.75rem', color: 'var(--danger)' }}>{c.risks[0]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">Discovery Questions</span>
            <span className="tag">From latest calls</span>
          </div>
          <div className="panel-body" style={{ display: 'grid', gap: '0.85rem' }}>
            {FAKE_CALLS.map((c) => (
              <div key={c.id}>
                <div className="row-title" style={{ marginBottom: '0.35rem' }}>{c.account}</div>
                <ul style={{ listStyle: 'none', display: 'grid', gap: '0.25rem' }}>
                  {c.questions.map((q) => (
                    <li key={q} style={{ fontSize: '0.78rem', color: 'var(--text-2)' }}>
                      <span style={{ color: 'var(--accent)' }}>?  </span>{q}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>

        <AskOracleWidget defaultQuestion="What are the TiFlash replication lag characteristics for a 10TB HTAP workload?" />
      </div>
    </>
  );
}
