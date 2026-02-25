'use client';

import { useState } from 'react';
import Image from 'next/image';

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const searchParams = typeof window !== 'undefined'
    ? new URLSearchParams(window.location.search)
    : new URLSearchParams();
  const errorParam = searchParams.get('error');

  const errorMessages = {
    no_pkce: 'Session expired. Please try again.',
    bad_pkce: 'Invalid session data. Please try again.',
    state_mismatch: 'Security check failed. Please try again.',
    no_code: 'No authorization code received.',
    exchange_failed: 'Could not exchange token with OpenAI. Please try again.',
    expired: 'Your session expired. Please log in again.',
  };

  const handleLogin = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/auth/start');
      const { url } = await res.json();
      window.location.href = url;
    } catch {
      setError('Failed to start login. Is the server running?');
      setLoading(false);
    }
  };

  return (
    <div className="login-shell">
      <div className="login-card">
        <div className="login-brand">
          <Image alt="TiDB" src="/tidb-logo.png" width={28} height={28} />
          <div>
            <div className="login-brand-name">TiDB Oracle</div>
            <div className="login-brand-sub">Internal GTM Copilot</div>
          </div>
        </div>

        <p className="login-heading">Sign in to continue</p>
        <p className="login-sub">
          Uses ChatGPT OAuth. For guaranteed API access, you can also configure `OPENAI_API_KEY`.
        </p>

        {(errorParam || error) && (
          <p className="error-text" style={{ marginBottom: '0.75rem' }}>
            {error || errorMessages[errorParam] || 'An error occurred.'}
          </p>
        )}

        <div className="login-btn-wrap">
          <button
            className="btn btn-primary"
            style={{ width: '100%', padding: '0.6rem 1rem' }}
            onClick={handleLogin}
            disabled={loading}
          >
            {loading ? 'Redirecting to OpenAI...' : 'Login with ChatGPT'}
          </button>
        </div>

        <div className="login-footer">
          Internal only. OAuth tokens are stored in a short-lived httpOnly cookie and never logged.
        </div>
      </div>
    </div>
  );
}
