import { NextResponse } from 'next/server';
import { generateVerifier, buildAuthUrl } from '../../../../lib/pkce';

export async function GET() {
  const verifier = generateVerifier();
  const { url, state } = buildAuthUrl(verifier);

  const res = NextResponse.json({ url });
  res.cookies.set('oracle_pkce', JSON.stringify({ verifier, state }), {
    httpOnly: true,
    sameSite: 'lax',
    path: '/',
    maxAge: 60 * 10,
  });
  return res;
}
