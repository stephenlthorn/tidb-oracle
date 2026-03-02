import { getSession } from '../../../lib/session';
import { apiGet } from '../../../lib/api';
import GoogleDrivePanel from '../../../components/GoogleDrivePanel';
import FeishuPanel from '../../../components/FeishuPanel';
import PersonaPromptPanel from '../../../components/PersonaPromptPanel';
import GTMFeaturePanel from '../../../components/GTMFeaturePanel';

export default async function SettingsPage() {
  const session = await getSession();
  const hasSession = Boolean(session?.access_token);

  const expiresIn = session?.expires_at
    ? Math.max(0, Math.round((session.expires_at - Date.now()) / 1000 / 60))
    : 0;

  let liveModel = 'gpt-5.3-codex';
  let personaName = 'sales_representative';
  let personaPrompt = '';
  let sePocKitUrl = '';
  let featureFlags = {};
  try {
    const cfg = await apiGet('/admin/kb-config');
    if (cfg?.llm_model) liveModel = cfg.llm_model;
    if (cfg?.persona_name) personaName = cfg.persona_name;
    if (cfg?.persona_prompt) personaPrompt = cfg.persona_prompt;
    if (cfg?.se_poc_kit_url) sePocKitUrl = cfg.se_poc_kit_url;
    if (cfg?.feature_flags_json && typeof cfg.feature_flags_json === 'object') featureFlags = cfg.feature_flags_json;
  } catch {
    // silently use default
  }

  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">Settings</div>
          <div className="topbar-meta">Connected account · preferences · session</div>
        </div>
      </div>

      <div className="content">
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">ChatGPT Account</span>
            <span className={`tag ${hasSession ? 'tag-green' : ''}`}>{hasSession ? 'Connected' : 'Not connected'}</span>
          </div>
          <div className="panel-body" style={{ display: 'grid', gap: '0.75rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr', gap: '0.5rem 1rem', fontSize: '0.82rem' }}>
              <span style={{ color: 'var(--text-3)' }}>Email</span>
              <span style={{ color: 'var(--text)' }}>{session?.email || '—'}</span>
              <span style={{ color: 'var(--text-3)' }}>Name</span>
              <span style={{ color: 'var(--text)' }}>{session?.name || '—'}</span>
              <span style={{ color: 'var(--text-3)' }}>Token expires</span>
              <span style={{ color: expiresIn < 10 ? 'var(--danger)' : 'var(--success)' }}>
                {expiresIn > 0 ? `~${expiresIn} min` : 'Expired'}
              </span>
              <span style={{ color: 'var(--text-3)' }}>Auth method</span>
              <span style={{ color: 'var(--text)' }}>{hasSession ? 'ChatGPT OAuth PKCE' : 'None'}</span>
              <span style={{ color: 'var(--text-3)' }}>Client ID</span>
              <span style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>app_EMoamEEZ73f0CkXaXp7hrann</span>
            </div>
            {hasSession ? (
              <form action="/api/auth/logout" method="POST" style={{ marginTop: '0.25rem' }}>
                <button type="submit" className="btn btn-danger">Sign out</button>
              </form>
            ) : (
              <a href="/login" className="btn btn-primary" style={{ display: 'inline-block', width: 'fit-content' }}>Login with ChatGPT</a>
            )}
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">LLM Configuration</span>
          </div>
          <div className="panel-body" style={{ display: 'grid', gap: '0.5rem', fontSize: '0.82rem' }}>
            {[
              { label: 'Model', value: `${liveModel}` },
              { label: 'Embedding Model', value: 'text-embedding-3-small' },
              { label: 'Retrieval Top-K', value: '8' },
              { label: 'Redact before LLM', value: 'Enabled' },
              { label: 'Direct API key', value: 'Set OPENAI_API_KEY in /Users/stephen/Documents/New project/.env for reliable Oracle responses' },
              { label: 'Codex OAuth', value: 'Also reads ~/.codex/auth.json (OPENAI_API_KEY or tokens.access_token)' },
            ].map(({ label, value }) => (
              <div key={label} style={{ display: 'grid', gridTemplateColumns: '160px 1fr', gap: '0.5rem' }}>
                <span style={{ color: 'var(--text-3)' }}>{label}</span>
                <span style={{ color: 'var(--text)' }}>{value}</span>
              </div>
            ))}
          </div>
        </div>

        <GoogleDrivePanel />
        <FeishuPanel />

        <PersonaPromptPanel initialPersona={personaName} initialPrompt={personaPrompt} />
        <GTMFeaturePanel initialPocKitUrl={sePocKitUrl} initialFeatureFlags={featureFlags} />

        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">Guardrails</span>
          </div>
          <div className="panel-body" style={{ display: 'grid', gap: '0.5rem', fontSize: '0.82rem' }}>
            {[
              { label: 'Internal-only messaging', value: 'Enabled — @pingcap.com only' },
              { label: 'Audit logging', value: 'All generation events logged' },
              { label: 'Email mode', value: 'Draft (no auto-send)' },
            ].map(({ label, value }) => (
              <div key={label} style={{ display: 'grid', gridTemplateColumns: '200px 1fr', gap: '0.5rem' }}>
                <span style={{ color: 'var(--text-3)' }}>{label}</span>
                <span style={{ color: 'var(--success)' }}>✓ {value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
