import { NextResponse } from 'next/server';
import { exchangeCode, parseIdToken } from '../../../../lib/pkce';

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const code = searchParams.get('code');
  const returnedState = searchParams.get('state');

  const pkceRaw = request.cookies.get('oracle_pkce')?.value;
  if (!pkceRaw) {
    return NextResponse.redirect(new URL('/login?error=no_pkce', request.url));
  }

  let pkce;
  try {
    pkce = JSON.parse(pkceRaw);
  } catch {
    return NextResponse.redirect(new URL('/login?error=bad_pkce', request.url));
  }

  if (pkce.state !== returnedState) {
    return NextResponse.redirect(new URL('/login?error=state_mismatch', request.url));
  }

  if (!code) {
    return NextResponse.redirect(new URL('/login?error=no_code', request.url));
  }

  let tokens;
  try {
    tokens = await exchangeCode(code, pkce.verifier);
  } catch (err) {
    console.error('Token exchange error:', err);
    return NextResponse.redirect(new URL('/login?error=exchange_failed', request.url));
  }

  const claims = tokens.id_token ? parseIdToken(tokens.id_token) : {};
  const session = {
    access_token: tokens.access_token,
    refresh_token: tokens.refresh_token || null,
    expires_at: Date.now() + (tokens.expires_in || 3600) * 1000,
    email: claims.email || 'user@openai.com',
    name: claims.name || claims.email || 'ChatGPT User',
  };

  const res = NextResponse.redirect(new URL('/rep', request.url));
  res.cookies.set('oracle_session', JSON.stringify(session), {
    httpOnly: true,
    sameSite: 'lax',
    path: '/',
    maxAge: 60 * 60 * 8,
  });
  res.cookies.set('oracle_pkce', '', { httpOnly: true, path: '/', maxAge: 0 });
  return res;
}
