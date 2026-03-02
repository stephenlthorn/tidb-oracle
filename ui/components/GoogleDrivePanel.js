'use client';

import { useEffect, useState } from 'react';

export default function GoogleDrivePanel() {
  const [status, setStatus] = useState(null);
  const [syncJob, setSyncJob] = useState(null);
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState('');

  const loadStatus = async () => {
    setLoadingStatus(true);
    try {
      const [statusRes, jobRes] = await Promise.all([
        fetch('/api/google-drive/status', { cache: 'no-store' }),
        fetch('/api/admin/sync/drive/jobs/latest', { cache: 'no-store' }),
      ]);
      const statusPayload = await statusRes.json();
      const jobPayload = await jobRes.json();
      setStatus(statusPayload);
      setSyncJob(jobPayload?.job || null);
    } catch {
      setMessage('Could not load Drive connection status.');
    } finally {
      setLoadingStatus(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  useEffect(() => {
    if (!syncJob?.job_id) return;
    if (!['queued', 'running'].includes(syncJob.status)) return;
    const timer = setInterval(async () => {
      try {
        const res = await fetch(`/api/admin/sync/drive/jobs/${syncJob.job_id}`, { cache: 'no-store' });
        const payload = await res.json();
        if (payload?.job) setSyncJob(payload.job);
      } catch {
        // keep polling
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [syncJob?.job_id, syncJob?.status]);

  const connectDrive = async () => {
    setWorking(true);
    setMessage('');
    try {
      const res = await fetch('/api/google-drive/oauth/start', { cache: 'no-store' });
      const payload = await res.json();
      if (!res.ok || !payload?.auth_url) {
        throw new Error(payload?.detail || payload?.error || 'Could not start Google OAuth flow.');
      }
      window.location.href = payload.auth_url;
    } catch (err) {
      setMessage(String(err?.message || err));
      setWorking(false);
    }
  };

  const disconnectDrive = async () => {
    setWorking(true);
    setMessage('');
    try {
      const res = await fetch('/api/google-drive/disconnect', { method: 'DELETE' });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload?.detail || payload?.error || 'Could not disconnect Google Drive.');
      setStatus(payload);
      setMessage('Google Drive disconnected.');
    } catch (err) {
      setMessage(String(err?.message || err));
    } finally {
      setWorking(false);
      loadStatus();
    }
  };

  const syncNow = async () => {
    setWorking(true);
    setMessage('');
    try {
      const res = await fetch('/api/admin/sync/drive/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ since: null }),
      });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload?.detail || payload?.error || 'Could not start Drive sync.');
      if (payload?.job) setSyncJob(payload.job);
      if (payload?.accepted === false && payload?.reason === 'already_running') {
        setMessage('Drive sync already running.');
      } else {
        setMessage('Drive sync started.');
      }
    } catch (err) {
      setMessage(String(err?.message || err));
    } finally {
      setWorking(false);
    }
  };

  const connected = Boolean(status?.connected);
  const filesSeen = Number(syncJob?.progress?.files_seen || 0);
  const processed = Number(syncJob?.progress?.processed || 0);
  const pct = filesSeen > 0 ? Math.min(100, Math.round((processed / filesSeen) * 100)) : 0;

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Google Drive Access</span>
        {loadingStatus ? (
          <span className="tag">Loading</span>
        ) : connected ? (
          <span className="tag tag-green">Connected</span>
        ) : (
          <span className="tag">Not connected</span>
        )}
      </div>
      <div className="panel-body" style={{ display: 'grid', gap: '0.75rem' }}>
        <p style={{ fontSize: '0.8rem', color: 'var(--text-2)' }}>
          Uses your own Google OAuth permissions. TiDB Oracle indexes what you can already access, including Shared Drives.
        </p>
        {connected && (
          <div style={{ display: 'grid', gap: '0.3rem', fontSize: '0.75rem', color: 'var(--text-3)' }}>
            <div>Scope: {status?.scopes?.join(', ') || 'drive.readonly'}</div>
            <div>Last synced: {status?.last_synced_at ? new Date(status.last_synced_at).toLocaleString() : 'Never'}</div>
          </div>
        )}

        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          {!connected ? (
            <button className="btn btn-primary" onClick={connectDrive} disabled={working}>
              Connect Google Drive
            </button>
          ) : (
            <>
              <button className="btn btn-primary" onClick={syncNow} disabled={working}>
                Sync My Drive
              </button>
              <button className="btn" onClick={disconnectDrive} disabled={working}>
                Disconnect
              </button>
            </>
          )}
        </div>

        {syncJob && (
          <div style={{ borderTop: '1px solid var(--border)', paddingTop: '0.6rem', display: 'grid', gap: '0.35rem' }}>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-3)' }}>
              Latest sync: {syncJob.status}
              {filesSeen > 0 ? ` · ${processed}/${filesSeen}` : ''}
            </div>
            {(syncJob.status === 'running' || syncJob.status === 'queued') && (
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
          </div>
        )}

        {message && <div style={{ fontSize: '0.78rem', color: 'var(--text-2)' }}>{message}</div>}
      </div>
    </div>
  );
}
