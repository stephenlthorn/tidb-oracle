import { apiGet } from '../../../lib/api';
import { FAKE_CALLS } from '../../../data/fake-calls';
import KBConfigPanel from '../../../components/KBConfigPanel';
import KnowledgeSourcesPanel from '../../../components/KnowledgeSourcesPanel';

const SAMPLE_AUDITS = [
  { id: '1', action: 'sync_drive', status: 'ok', actor: 'system', ts: '2026-02-19T10:02:00Z' },
  { id: '2', action: 'sync_chorus', status: 'ok', actor: 'system', ts: '2026-02-19T10:05:00Z' },
  { id: '3', action: 'chat', status: 'ok', actor: 'estyn.c@pingcap.com', ts: '2026-02-19T10:12:00Z' },
  { id: '4', action: 'draft_message', status: 'ok', actor: 'maya.t@pingcap.com', ts: '2026-02-19T11:01:00Z' },
  { id: '5', action: 'chat', status: 'error', actor: 'jordan.r@pingcap.com', ts: '2026-02-19T11:45:00Z' },
];

const SAMPLE_DOCS = [
  { title: 'TiDB GTM Positioning Playbook', source_type: 'google_drive', source_id: 'drive_001', modified_time: '2026-02-18' },
  { title: 'TiFlash Sizing FAQ', source_type: 'google_drive', source_id: 'drive_002', modified_time: '2026-02-18' },
  { title: 'Online DDL Objection Handling', source_type: 'google_drive', source_id: 'drive_003', modified_time: '2026-02-18' },
  { title: 'Feishu: Enterprise Security FAQ', source_type: 'feishu', source_id: 'feishu_001', modified_time: '2026-02-18' },
];

export default async function AdminPage() {
  const [docsRaw, auditsRaw] = await Promise.all([
    apiGet('/kb/documents?limit=300').catch(() => []),
    apiGet('/admin/audit?limit=30').catch(() => []),
  ]);

  const docs = docsRaw.length ? docsRaw : SAMPLE_DOCS;
  const audits = auditsRaw.length ? auditsRaw : SAMPLE_AUDITS;
  const sampleMode = !docsRaw.length;

  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">Admin</div>
          <div className="topbar-meta">Data coverage · audit log · sync status</div>
        </div>
        <div className="topbar-right">
          <span className={`tag ${sampleMode ? '' : 'tag-green'}`}>{sampleMode ? 'Sample data' : 'Live data'}</span>
        </div>
      </div>

      <div className="content">
        <div className="kpi-row">
          {[
            { label: 'Docs Indexed', value: docs.length, sub: docs[0]?.title || '—' },
            { label: 'Calls Indexed', value: FAKE_CALLS.length, sub: 'Evernorth · Northwind · Summit' },
            { label: 'Audit Events', value: audits.length, sub: 'Last 30 days' },
          ].map((k) => (
            <div className="kpi-card" key={k.label}>
              <div className="kpi-label">{k.label}</div>
              <div className="kpi-value">{k.value}</div>
              <div className="kpi-sub">{k.sub}</div>
            </div>
          ))}
        </div>

        <KBConfigPanel />

        <div className="two-col">
          <KnowledgeSourcesPanel docs={docs} />

          <div className="panel">
            <div className="panel-header">
              <span className="panel-title">Audit Log</span>
            </div>
            <table className="data-table">
              <thead>
                <tr><th>Action</th><th>Actor</th><th>Status</th><th>Time</th></tr>
              </thead>
              <tbody>
                {audits.slice(0, 10).map((a) => (
                  <tr key={a.id}>
                    <td className="row-title">{a.action}</td>
                    <td style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>{a.actor || a.actor_email || '—'}</td>
                    <td>
                      <span className={`tag ${a.status === 'ok' ? 'tag-green' : 'tag-red'}`}>
                        {a.status}
                      </span>
                    </td>
                    <td style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>
                      {new Date(a.ts || a.timestamp || 0).toLocaleTimeString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
