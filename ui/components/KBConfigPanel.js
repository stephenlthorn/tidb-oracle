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
  const [message, setMessage] = useState('');

  useEffect(() => {
    fetch('/api/admin/kb-config')
      .then(r => r.json())
      .then(data => setConfig(data))
      .catch(() => setMessage('Failed to load KB config'));
  }, []);

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
      setMessage('✓ ' + (data.message || 'Sync triggered'));
    } catch {
      setMessage('✗ Sync failed');
    } finally {
      setSyncing(false);
    }
  };

  const set = (key, value) => setConfig(prev => ({ ...prev, [key]: value }));

  if (!config) {
    return <div className="panel" style={{ opacity: 0.6 }}>Loading KB config…</div>;
  }

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
        {config.google_drive_enabled && (
          <input
            className="input"
            placeholder="Comma-separated folder IDs"
            value={config.google_drive_folder_ids || ''}
            onChange={e => set('google_drive_folder_ids', e.target.value)}
            style={{ width: '100%', fontFamily: 'monospace', fontSize: '0.75rem' }}
          />
        )}
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
            <input
              className="input"
              placeholder="Folder Token"
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

      {/* Actions */}
      <div style={{ borderTop: '1px solid var(--border)', paddingTop: '1rem', display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
        <button className="btn btn-primary" onClick={save} disabled={saving}>
          {saving ? 'Saving…' : 'Save Config'}
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
    </div>
  );
}
