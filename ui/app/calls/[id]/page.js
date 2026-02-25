import { FAKE_CALLS } from '../../../data/fake-calls';
import Link from 'next/link';

export default async function CallPage({ params }) {
  const { id } = await params;
  const call = FAKE_CALLS.find((c) => c.id === id);

  if (!call) {
    return (
      <div style={{ padding: '2rem' }}>
        <p style={{ color: 'var(--text-3)', marginBottom: '1rem' }}>Call not found: {id}</p>
        <Link href="/rep">← Back to Rep</Link>
      </div>
    );
  }

  return (
    <div style={{ padding: '1.25rem', display: 'grid', gap: '1rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <Link href="/rep" style={{ color: 'var(--text-3)', fontSize: '0.78rem' }}>← Back</Link>
        <span className="tag">{call.stage}</span>
        <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{call.arr}</span>
      </div>

      <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text)' }}>
        {call.account} — {call.date}
      </div>

      <div className="two-col">
        <div className="panel">
          <div className="panel-header"><span className="panel-title">Call Summary</span></div>
          <div className="panel-body" style={{ fontSize: '0.82rem', color: 'var(--text-2)', lineHeight: 1.6 }}>
            {call.summary}
          </div>
        </div>

        <div className="panel">
          <div className="panel-header"><span className="panel-title">Metadata</span></div>
          <div className="panel-body" style={{ display: 'grid', gap: '0.4rem', fontSize: '0.8rem' }}>
            {[
              { label: 'Duration', value: call.duration },
              { label: 'Competitor', value: call.competitor },
              { label: 'Participants', value: call.participants.join(', ') },
            ].map(({ label, value }) => (
              <div key={label} style={{ display: 'grid', gridTemplateColumns: '90px 1fr' }}>
                <span style={{ color: 'var(--text-3)' }}>{label}</span>
                <span style={{ color: 'var(--text)' }}>{value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="three-col">
        <div className="panel">
          <div className="panel-header"><span className="panel-title">Risks</span></div>
          <div className="panel-body">
            <ul style={{ listStyle: 'none', display: 'grid', gap: '0.45rem' }}>
              {call.risks.map((r) => (
                <li key={r} style={{ fontSize: '0.78rem', color: 'var(--danger)' }}>⚠ {r}</li>
              ))}
            </ul>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header"><span className="panel-title">Next Steps</span></div>
          <div className="panel-body">
            <ul style={{ listStyle: 'none', display: 'grid', gap: '0.45rem' }}>
              {call.nextSteps.map((s) => (
                <li key={s} style={{ fontSize: '0.78rem', color: 'var(--text-2)' }}>→ {s}</li>
              ))}
            </ul>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header"><span className="panel-title">Collateral</span></div>
          <div className="panel-body">
            <ul style={{ listStyle: 'none', display: 'grid', gap: '0.45rem' }}>
              {call.collateral.map((c) => (
                <li key={c.title} style={{ fontSize: '0.78rem' }}>
                  <a href={c.url} style={{ color: 'var(--accent)' }}>↗ {c.title}</a>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-header"><span className="panel-title">Transcript</span></div>
        <div className="panel-body">
          <pre style={{ maxHeight: '320px' }}>{call.transcript}</pre>
        </div>
      </div>
    </div>
  );
}
