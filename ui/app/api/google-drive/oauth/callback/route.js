import { NextResponse } from 'next/server';
import { getSession } from '@/lib/session';

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000';

export async function GET(request) {
  const session = await getSession();
  if (!session?.email) {
    return NextResponse.redirect(new URL('/login', request.url));
  }

  const url = new URL(request.url);
  const code = url.searchParams.get('code');
  const state = url.searchParams.get('state');
  const error = url.searchParams.get('error');
  const redirectUri = new URL('/api/google-drive/oauth/callback', request.url).toString();

  if (error) {
    return NextResponse.redirect(new URL(`/settings?drive=error&reason=${encodeURIComponent(error)}`, request.url));
  }
  if (!code || !state) {
    return NextResponse.redirect(new URL('/settings?drive=error&reason=missing_code_or_state', request.url));
  }

  const res = await fetch(`${API_BASE}/admin/drive/oauth/exchange`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Email': session.email,
      ...(session.access_token ? { 'X-OpenAI-Token': session.access_token } : {}),
    },
    body: JSON.stringify({
      code,
      state,
      redirect_uri: redirectUri,
      user_email: session.email,
    }),
  });

  if (!res.ok) {
    return NextResponse.redirect(new URL('/settings?drive=error&reason=token_exchange_failed', request.url));
  }
  return NextResponse.redirect(new URL('/settings?drive=connected', request.url));
}
