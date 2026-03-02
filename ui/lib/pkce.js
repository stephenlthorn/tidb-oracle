import crypto from 'crypto';

export function generateVerifier() {
  return crypto.randomBytes(32).toString('base64url');
}

export function generateChallenge(verifier) {
  const hash = crypto.createHash('sha256').update(verifier).digest();
  return Buffer.from(hash).toString('base64url');
}

export function buildAuthUrl(verifier) {
  const challenge = generateChallenge(verifier);
  const state = crypto.randomBytes(16).toString('hex');
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: 'app_EMoamEEZ73f0CkXaXp7hrann',
    redirect_uri: 'http://localhost:1455/auth/callback',
    scope: 'openid profile email offline_access',
    code_challenge: challenge,
    code_challenge_method: 'S256',
    state,
    id_token_add_organizations: 'true',
    codex_cli_simplified_flow: 'true',
  });
  return {
    url: `https://auth.openai.com/oauth/authorize?${params}`,
    state,
  };
}

export async function exchangeCode(code, verifier) {
  const res = await fetch('https://auth.openai.com/oauth/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      client_id: 'app_EMoamEEZ73f0CkXaXp7hrann',
      code,
      code_verifier: verifier,
      redirect_uri: 'http://localhost:1455/auth/callback',
    }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Token exchange failed: ${res.status} ${body}`);
  }
  return res.json();
}

export function parseIdToken(idToken) {
  // JWT decode (no verification — demo tool; in prod verify with JWKS)
  const parts = idToken.split('.');
  if (parts.length < 2) return {};
  try {
    return JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8'));
  } catch {
    return {};
  }
}
