'use client';

import { useState } from 'react';

function parseFlags(input) {
  const lines = input.split('\n').map((line) => line.trim()).filter(Boolean);
  const flags = {};
  for (const line of lines) {
    const [keyRaw, valueRaw] = line.split('=').map((item) => item?.trim());
    if (!keyRaw) continue;
    const value = (valueRaw || 'true').toLowerCase();
    flags[keyRaw] = value === 'true' || value === '1' || value === 'yes';
  }
  return flags;
}

function flagsToText(flags) {
  if (!flags || typeof flags !== 'object') return '';
  return Object.entries(flags).map(([key, value]) => `${key}=${value ? 'true' : 'false'}`).join('\n');
}

export default function GTMFeaturePanel({ initialPocKitUrl = '', initialFeatureFlags = {} }) {
  const [pocKitUrl, setPocKitUrl] = useState(initialPocKitUrl || '');
  const [flagText, setFlagText] = useState(flagsToText(initialFeatureFlags));
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  const save = async () => {
    setSaving(true);
    setMessage('');
    try {
      const res = await fetch('/api/admin/kb-config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          se_poc_kit_url: pocKitUrl.trim() || null,
          feature_flags_json: parseFlags(flagText),
        }),
      });
      if (!res.ok) throw new Error('Failed to save GTM settings');
      setMessage('Saved.');
    } catch {
      setMessage('Could not save GTM settings.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">GTM Module Settings</span>
      </div>
      <div className="panel-body" style={{ display: 'grid', gap: '0.75rem' }}>
        <div style={{ display: 'grid', gap: '0.35rem' }}>
          <label style={{ color: 'var(--text-3)', fontSize: '0.74rem' }}>SE POC Kit URL</label>
          <input
            className="input"
            value={pocKitUrl}
            onChange={(e) => setPocKitUrl(e.target.value)}
            placeholder="https://..."
          />
        </div>

        <div style={{ display: 'grid', gap: '0.35rem' }}>
          <label style={{ color: 'var(--text-3)', fontSize: '0.74rem' }}>Feature Flags (key=true|false)</label>
          <textarea
            className="input"
            rows={5}
            value={flagText}
            onChange={(e) => setFlagText(e.target.value)}
            placeholder="rep_account_brief=true\nse_competitor_coach=true"
          />
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <button className="btn btn-primary" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : 'Save GTM Settings'}
          </button>
          {message && (
            <span style={{ color: message === 'Saved.' ? 'var(--success)' : 'var(--danger)', fontSize: '0.75rem' }}>
              {message}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
