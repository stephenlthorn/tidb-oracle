'use client';

import { useState, useEffect } from 'react';

const MODELS = [
  { id: 'gpt-5.3-codex',    label: '5.3 Codex' },
  { id: 'gpt-5.2-codex',    label: '5.2 Codex' },
  { id: 'gpt-5.1-codex',    label: '5.1 Codex' },
  { id: 'gpt-5.1',          label: 'GPT-5.1'   },
  { id: 'gpt-5-codex-mini', label: 'Mini'      },
];

export default function KBConfigPanel() {
  const [config, setConfig] = useState(null);
  const [saving, setSaving] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [driveSyncing, setDriveSyncing] = useState(false);
  const [driveJob, setDriveJob] = useState(null);
  const [message, setMessage] = useState('');

  useEffect(() => {
    fetch('/api/admin/kb-config')
      .then(r => r.json())
      .then(data => setConfig(data))
      .catch(() => setMessage('Failed to load KB config'));

    fetch('/api/admin/sync/drive/jobs/latest')
      .then(r => r.json())
      .then(data => {
        if (data?.job) setDriveJob(data.job);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!driveJob?.job_id) return;
    if (!['queued', 'running'].includes(driveJob.status)) return;

    const timer = setInterval(async () => {
      try {
        const res = await fetch(`/api/admin/sync/drive/jobs/${driveJob.job_id}`, { cache: 'no-store' });
        const data = await res.json();
        if (data?.job) {
          setDriveJob(data.job);
          if (!['queued', 'running'].includes(data.job.status)) {
            setDriveSyncing(false);
          }
        }
      } catch {
        // keep polling until user refreshes or job settles
      }
    }, 2000);

    return () => clearInterval(timer);
  }, [driveJob?.job_id, driveJob?.status]);

  const save = async () => {
    setSaving(true);
    setMessage('');
    try {
      const res = await fetch('/api/admin/kb-config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      if (!res.ok) throw new Error('Save failed');
      const updated = await res.json();
      setConfig(updated);
      setMessage('✓ Saved');
    } catch {
      setMessage('✗ Save failed');
    } finally {
      setSaving(false);
    }
  };

  const syncFeishu = async () => {
    setSyncing(true);
    setMessage('');
    try {
      const res = await fetch('/api/admin/sync/feishu', { method: 'POST' });
      const data = await res.json();
      if (!res.ok || data?.status === 'error') {
        throw new Error(data?.message || data?.detail || 'Sync failed');
      }
      const indexed = Number(data?.added || 0) + Number(data?.updated || 0);
      const errors = Number(data?.errors || 0);
      const firstError = data?.error_samples?.[0]?.error || '';
      if (errors > 0) {
        setMessage(
          `✓ Feishu sync ${data?.status === 'partial' ? 'partial' : 'complete'} ` +
          `(${indexed} indexed, ${Number(data?.skipped || 0)} skipped, ${errors} errors) ${firstError}`
        );
      } else {
        setMessage(`✓ Feishu sync complete (${indexed} indexed, ${Number(data?.skipped || 0)} skipped)`);
      }
    } catch {
      setMessage('✗ Sync failed');
    } finally {
      setSyncing(false);
    }
  };

  const startDriveSync = async () => {
    setDriveSyncing(true);
    setMessage('');
    try {
      const res = await fetch('/api/admin/sync/drive/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ since: null }),
      });
      const data = await res.json();
      if (data?.job) {
        setDriveJob(data.job);
      }
      if (data?.accepted === false && data?.reason === 'already_running') {
        setMessage('Drive sync already running — showing live status.');
      } else {
        setMessage('✓ Drive sync started in background');
      }
    } catch {
      setMessage('✗ Failed to start Drive sync');
      setDriveSyncing(false);
    }
  };

  const set = (key, value) => setConfig(prev => ({ ...prev, [key]: value }));

  if (!config) {
    return <div className="panel" style={{ opacity: 0.6 }}>Loading KB config…</div>;
  }

  const driveProgress = driveJob?.progress || {};
  const filesSeen = Number(driveProgress.files_seen || 0);
  const processed = Number(driveProgress.processed || 0);
  const pct = filesSeen > 0 ? Math.min(100, Math.round((processed / filesSeen) * 100)) : 0;
  const featureFlagsText = JSON.stringify(config.feature_flags_json || {}, null, 2);

  return (
    <div className="panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <h3 style={{ margin: 0, fontSize: '0.9rem', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--dim)' }}>
        Knowledge Base Configuration
      </h3>

      {/* Retrieval depth */}
      <div>
        <label style={{ fontSize: '0.8rem', color: 'var(--dim)', display: 'block', marginBottom: '0.5rem' }}>
          RETRIEVAL DEPTH (top-k chunks)
        </label>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {[4, 8, 12, 20].map(k => (
            <button
              key={k}
              className={config.retrieval_top_k === k ? 'btn btn-primary' : 'btn'}
              style={{ minWidth: '3rem' }}
              onClick={() => set('retrieval_top_k', k)}
            >
              {k}
            </button>
          ))}
        </div>
      </div>

      {/* Model selector */}
      <div style={{ borderTop: '1px solid var(--border)', paddingTop: '1rem' }}>
        <label style={{ fontSize: '0.8rem', color: 'var(--dim)', display: 'block', marginBottom: '0.5rem' }}>
          LLM MODEL
        </label>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          {MODELS.map(m => (
            <button
              key={m.id}
              className={config.llm_model === m.id ? 'btn btn-primary' : 'btn'}
              style={{ fontSize: '0.75rem' }}
              onClick={() => set('llm_model', m.id)}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tool toggles */}
      <div style={{ borderTop: '1px solid var(--border)', paddingTop: '1rem' }}>
        <label style={{ fontSize: '0.8rem', color: 'var(--dim)', display: 'block', marginBottom: '0.75rem' }}>
          TOOLS
        </label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={!!config.web_search_enabled}
              onChange={e => set('web_search_enabled', e.target.checked)}
            />
            <span style={{ fontSize: '0.82rem' }}>Web Search</span>
            <span style={{ fontSize: '0.75rem', color: 'var(--dim)' }}>— ChatGPT searches the web when relevant</span>
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={!!config.code_interpreter_enabled}
              onChange={e => set('code_interpreter_enabled', e.target.checked)}
            />
            <span style={{ fontSize: '0.82rem' }}>Code Interpreter</span>
            <span style={{ fontSize: '0.75rem', color: 'var(--dim)' }}>— run Python, analyse data</span>
          </label>
        </div>
      </div>

      {/* Google Drive */}
      <div style={{ borderTop: '1px solid var(--border)', paddingTop: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem' }}>
          <label style={{ fontSize: '0.8rem', color: 'var(--dim)', textTransform: 'uppercase' }}>Google Drive</label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={!!config.google_drive_enabled}
              onChange={e => set('google_drive_enabled', e.target.checked)}
            />
            <span style={{ fontSize: '0.8rem' }}>Enabled</span>
          </label>
        </div>
        <div style={{ fontSize: '0.75rem', color: 'var(--text-3)' }}>
          Per-user OAuth mode enabled: users can index/search files they already have access to, including Shared Drives.
        </div>
      </div>

      {/* Feishu */}
      <div style={{ borderTop: '1px solid var(--border)', paddingTop: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem' }}>
          <label style={{ fontSize: '0.8rem', color: 'var(--dim)', textTransform: 'uppercase' }}>Feishu / Lark</label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={!!config.feishu_enabled}
              onChange={e => set('feishu_enabled', e.target.checked)}
            />
            <span style={{ fontSize: '0.8rem' }}>Enabled</span>
          </label>
        </div>
        {config.feishu_enabled && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.8rem' }}>
              <input
                type="checkbox"
                checked={!!config.feishu_oauth_enabled}
                onChange={e => set('feishu_oauth_enabled', e.target.checked)}
              />
              <span>Per-user OAuth mode</span>
            </label>
            <textarea
              className="input"
              rows={3}
              placeholder="Root tokens (one per line or comma-separated). Leave blank for global crawl."
              value={config.feishu_root_tokens || config.feishu_folder_token || ''}
              onChange={e => {
                const value = e.target.value;
                set('feishu_root_tokens', value);
                const first = value.split(/[\n,]/)[0]?.trim() || '';
                set('feishu_folder_token', first);
              }}
            />
            <input
              className="input"
              placeholder="Legacy Folder Token (optional)"
              value={config.feishu_folder_token || ''}
              onChange={e => set('feishu_folder_token', e.target.value)}
            />
            <input
              className="input"
              placeholder="App ID"
              value={config.feishu_app_id || ''}
              onChange={e => set('feishu_app_id', e.target.value)}
            />
            <input
              className="input"
              type="password"
              placeholder="App Secret (write-only)"
              onChange={e => set('feishu_app_secret', e.target.value)}
            />
          </div>
        )}
      </div>

      {/* Chorus */}
      <div style={{ borderTop: '1px solid var(--border)', paddingTop: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <label style={{ fontSize: '0.8rem', color: 'var(--dim)', textTransform: 'uppercase' }}>Chorus Calls</label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={!!config.chorus_enabled}
              onChange={e => set('chorus_enabled', e.target.checked)}
            />
            <span style={{ fontSize: '0.8rem' }}>Enabled</span>
          </label>
        </div>
      </div>

      {/* GTM modules */}
      <div style={{ borderTop: '1px solid var(--border)', paddingTop: '1rem', display: 'grid', gap: '0.6rem' }}>
        <label style={{ fontSize: '0.8rem', color: 'var(--dim)', textTransform: 'uppercase' }}>GTM Modules</label>
        <input
          className="input"
          placeholder="SE POC kit URL (optional)"
          value={config.se_poc_kit_url || ''}
          onChange={(e) => set('se_poc_kit_url', e.target.value)}
        />
        <textarea
          className="input"
          rows={4}
          defaultValue={featureFlagsText}
          onBlur={(e) => {
            try {
              const parsed = JSON.parse(e.target.value || '{}');
              set('feature_flags_json', parsed);
            } catch {
              // preserve current object until valid JSON is entered
            }
          }}
          placeholder='{"rep_account_brief": true, "se_poc_plan": true}'
        />
      </div>

      {/* Actions */}
      <div style={{ borderTop: '1px solid var(--border)', paddingTop: '1rem', display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <button className="btn btn-primary" onClick={save} disabled={saving}>
          {saving ? 'Saving…' : 'Save Config'}
        </button>
        <button className="btn" onClick={startDriveSync} disabled={driveSyncing || driveJob?.status === 'running' || driveJob?.status === 'queued'}>
          {driveSyncing || driveJob?.status === 'running' || driveJob?.status === 'queued' ? 'Drive Sync Running…' : 'Sync Drive (Background)'}
        </button>
        {config.feishu_enabled && (
          <button className="btn" onClick={syncFeishu} disabled={syncing}>
            {syncing ? 'Syncing…' : 'Sync Feishu Now'}
          </button>
        )}
        {message && (
          <span style={{ fontSize: '0.8rem', color: message.startsWith('✓') ? 'var(--accent)' : '#ef4444' }}>
            {message}
          </span>
        )}
      </div>

      {driveJob && (
        <div style={{ borderTop: '1px solid var(--border)', paddingTop: '1rem', display: 'grid', gap: '0.45rem' }}>
          <div style={{ fontSize: '0.78rem', color: 'var(--dim)', textTransform: 'uppercase' }}>Drive Sync Job</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            <span className={`tag ${driveJob.status === 'completed' ? 'tag-green' : driveJob.status === 'failed' ? 'tag-red' : ''}`}>
              {driveJob.status}
            </span>
            <span style={{ fontSize: '0.76rem', color: 'var(--text-3)', fontFamily: 'monospace' }}>
              {driveJob.job_id?.slice(0, 8)}
            </span>
            {filesSeen > 0 && (
              <span style={{ fontSize: '0.76rem', color: 'var(--text-3)' }}>
                {processed}/{filesSeen} ({pct}%)
              </span>
            )}
          </div>
          {(driveJob.status === 'running' || driveJob.status === 'queued') && (
            <div style={{ height: '6px', background: 'var(--bg-soft)', borderRadius: '999px', overflow: 'hidden' }}>
              <div
                style={{
                  width: `${filesSeen > 0 ? pct : 15}%`,
                  height: '100%',
                  background: 'var(--accent)',
                  transition: 'width 300ms ease',
                }}
              />
            </div>
          )}
          {driveJob.result && (
            <div style={{ fontSize: '0.78rem', color: 'var(--text-2)' }}>
              Indexed: {driveJob.result.indexed ?? 0} · Skipped: {driveJob.result.skipped ?? 0} · Files seen: {driveJob.result.files_seen ?? 0}
            </div>
          )}
          {driveJob.error && (
            <div style={{ fontSize: '0.78rem', color: '#ef4444' }}>
              {driveJob.error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
