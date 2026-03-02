'use client';

import { useEffect, useState } from 'react';

export default function FeishuPanel() {
  const [status, setStatus] = useState(null);
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const [statusRes, cfgRes] = await Promise.all([
        fetch('/api/feishu/status', { cache: 'no-store' }),
        fetch('/api/admin/kb-config', { cache: 'no-store' }),
      ]);
      const statusPayload = await statusRes.json();
      const cfgPayload = await cfgRes.json();
      setStatus(statusPayload);
      setConfig(cfgPayload);
    } catch {
      setMessage('Could not load Feishu settings.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const setCfg = (key, value) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
  };

  const saveConfig = async () => {
    if (!config) return;
    setWorking(true);
    setMessage('');
    try {
      const payload = {
        feishu_enabled: !!config.feishu_enabled,
        feishu_oauth_enabled: !!config.feishu_oauth_enabled,
        feishu_root_tokens: config.feishu_root_tokens || '',
        feishu_folder_token: config.feishu_folder_token || '',
        feishu_app_id: config.feishu_app_id || '',
      };
      if (config.__new_secret) {
        payload.feishu_app_secret = config.__new_secret;
      }

      const res = await fetch('/api/admin/kb-config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || 'Failed to save Feishu config.');
      setConfig({ ...data, __new_secret: '' });
      setMessage('Feishu settings saved.');
    } catch (err) {
      setMessage(String(err?.message || err));
    } finally {
      setWorking(false);
    }
  };

  const connect = async () => {
    setWorking(true);
    setMessage('');
    try {
      const res = await fetch('/api/feishu/oauth/start', { cache: 'no-store' });
      const payload = await res.json();
      if (!res.ok || !payload?.auth_url) {
        throw new Error(payload?.detail || payload?.error || 'Could not start Feishu OAuth.');
      }
      window.location.href = payload.auth_url;
    } catch (err) {
      setMessage(String(err?.message || err));
      setWorking(false);
    }
  };

  const disconnect = async () => {
    setWorking(true);
    setMessage('');
    try {
      const res = await fetch('/api/feishu/disconnect', { method: 'DELETE' });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload?.detail || payload?.error || 'Could not disconnect Feishu.');
      setStatus(payload);
      setMessage('Feishu disconnected.');
    } catch (err) {
      setMessage(String(err?.message || err));
    } finally {
      setWorking(false);
      load();
    }
  };

  const syncNow = async () => {
    setWorking(true);
    setMessage('');
    try {
      const res = await fetch('/api/admin/sync/feishu', { method: 'POST' });
      const payload = await res.json();
      if (!res.ok || payload?.status === 'error') {
        throw new Error(payload?.message || payload?.detail || 'Feishu sync failed.');
      }
      const indexed = Number(payload?.added || 0) + Number(payload?.updated || 0);
      const errors = Number(payload?.errors || 0);
      const firstError = payload?.error_samples?.[0]?.error || '';
      if (errors > 0) {
        setMessage(
          `Feishu sync ${payload?.status === 'partial' ? 'partial' : 'complete'}: ` +
            `${indexed} indexed, ${Number(payload?.skipped || 0)} skipped, ${errors} errors. ` +
            `${firstError}`
        );
      } else {
        setMessage(`Feishu sync complete: indexed ${indexed}, skipped ${Number(payload?.skipped || 0)}.`);
      }
      load();
    } catch (err) {
      setMessage(String(err?.message || err));
    } finally {
      setWorking(false);
    }
  };

  const connected = Boolean(status?.connected);

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Feishu / Lark Access</span>
        {loading ? (
          <span className="tag">Loading</span>
        ) : connected ? (
          <span className="tag tag-green">Connected</span>
        ) : (
          <span className="tag">Not connected</span>
        )}
      </div>

      <div className="panel-body" style={{ display: 'grid', gap: '0.75rem' }}>
        <p style={{ fontSize: '0.8rem', color: 'var(--text-2)' }}>
          Configure one or more root tokens and optional per-user OAuth mode. Leave roots blank to run global crawl.
        </p>

        {config && (
          <>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8rem' }}>
              <input
                type="checkbox"
                checked={!!config.feishu_enabled}
                onChange={(e) => setCfg('feishu_enabled', e.target.checked)}
              />
              Enable Feishu source
            </label>

            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8rem' }}>
              <input
                type="checkbox"
                checked={!!config.feishu_oauth_enabled}
                onChange={(e) => setCfg('feishu_oauth_enabled', e.target.checked)}
              />
              Per-user OAuth inheritance
            </label>

            <textarea
              className="input"
              rows={4}
              placeholder="Root tokens (one per line or comma-separated). Leave blank for global crawl."
              value={config.feishu_root_tokens || config.feishu_folder_token || ''}
              onChange={(e) => {
                setCfg('feishu_root_tokens', e.target.value);
                setCfg('feishu_folder_token', e.target.value.split(/[\n,]/)[0]?.trim() || '');
              }}
            />

            <input
              className="input"
              placeholder="Feishu App ID"
              value={config.feishu_app_id || ''}
              onChange={(e) => setCfg('feishu_app_id', e.target.value)}
            />

            <input
              className="input"
              type="password"
              placeholder="Feishu App Secret (leave blank to keep current)"
              value={config.__new_secret || ''}
              onChange={(e) => setCfg('__new_secret', e.target.value)}
            />

            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <button className="btn btn-primary" onClick={saveConfig} disabled={working}>
                Save Feishu Settings
              </button>

              {config.feishu_oauth_enabled ? (
                !connected ? (
                  <button className="btn" onClick={connect} disabled={working}>
                    Connect Feishu
                  </button>
                ) : (
                  <button className="btn" onClick={disconnect} disabled={working}>
                    Disconnect
                  </button>
                )
              ) : null}

              <button className="btn" onClick={syncNow} disabled={working || !config.feishu_enabled}>
                Sync Feishu
              </button>
            </div>
          </>
        )}

        {connected && (
          <div style={{ fontSize: '0.75rem', color: 'var(--text-3)' }}>
            Last synced: {status?.last_synced_at ? new Date(status.last_synced_at).toLocaleString() : 'Never'}
          </div>
        )}

        {message && <div style={{ fontSize: '0.78rem', color: 'var(--text-2)' }}>{message}</div>}
      </div>
    </div>
  );
}
