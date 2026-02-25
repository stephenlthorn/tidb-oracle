import { FAKE_PRIORITIES, FAKE_COACHING, FAKE_CALLS } from '../../../data/fake-calls';
import AskOracleWidget from '../../../components/AskOracleWidget';
import Link from 'next/link';

export default function RepPage() {
  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">Sales Rep</div>
          <div className="topbar-meta">Deal priorities · call coaching · follow-ups</div>
        </div>
        <div className="topbar-right">
          <span className="tag tag-orange">3 active deals</span>
          <span className="tag">Sample data</span>
        </div>
      </div>

      <div className="content">
        <div className="kpi-row">
          {[
            { label: 'Deals in Motion', value: '3', sub: 'Technical Validation → Business Case' },
            { label: 'Open Follow-Ups', value: '7', sub: '3 past due' },
            { label: 'Risk Flags', value: '3', sub: 'All high-priority accounts' },
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
              <span className="panel-title">Deal Priorities</span>
              <span className="tag">Top 3</span>
            </div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Stage</th>
                  <th>Value</th>
                  <th>Risk</th>
                </tr>
              </thead>
              <tbody>
                {FAKE_PRIORITIES.map((d) => (
                  <tr key={d.account}>
                    <td className="row-title">{d.account}</td>
                    <td>{d.stage}</td>
                    <td style={{ color: 'var(--accent)' }}>{d.value}</td>
                    <td style={{ color: 'var(--danger)', fontSize: '0.75rem' }}>{d.risk}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="panel">
            <div className="panel-header">
              <span className="panel-title">Call Coaching</span>
              <span className="tag tag-green">Fresh</span>
            </div>
            <div className="panel-body" style={{ display: 'grid', gap: '0.75rem' }}>
              {FAKE_COACHING.map((item) => (
                <div key={item.account} style={{ borderBottom: '1px solid var(--border)', paddingBottom: '0.65rem' }}>
                  <div className="row-title" style={{ marginBottom: '0.3rem' }}>{item.account}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-2)', marginBottom: '0.25rem' }}>{item.happened}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--accent)' }}>→ {item.next}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">Recent Calls</span>
            <span className="tag">{FAKE_CALLS.length} indexed</span>
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Account</th>
                <th>Date</th>
                <th>Duration</th>
                <th>Stage</th>
                <th>Next Action</th>
              </tr>
            </thead>
            <tbody>
              {FAKE_CALLS.map((c) => (
                <tr key={c.id}>
                  <td>
                    <Link href={`/calls/${c.id}`} className="row-title" style={{ color: 'var(--accent)' }}>
                      {c.account}
                    </Link>
                  </td>
                  <td>{c.date}</td>
                  <td>{c.duration}</td>
                  <td>{c.stage}</td>
                  <td style={{ fontSize: '0.75rem' }}>{c.nextSteps[0]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <AskOracleWidget defaultQuestion="How should we position TiDB vs SingleStore for a 40TB analytics workload?" />
      </div>
    </>
  );
}
