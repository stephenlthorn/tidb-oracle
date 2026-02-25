import { cookies } from 'next/headers';

const COOKIE_NAME = 'oracle_session';
const PKCE_COOKIE = 'oracle_pkce';
const MAX_AGE = 60 * 60 * 8; // 8 hours

export function setSession(res, session) {
  res.cookies.set(COOKIE_NAME, JSON.stringify(session), {
    httpOnly: true,
    sameSite: 'lax',
    path: '/',
    maxAge: MAX_AGE,
  });
}

export function clearSession(res) {
  res.cookies.set(COOKIE_NAME, '', { httpOnly: true, path: '/', maxAge: 0 });
}

export function setPkceCookie(res, verifier, state) {
  res.cookies.set(PKCE_COOKIE, JSON.stringify({ verifier, state }), {
    httpOnly: true,
    sameSite: 'lax',
    path: '/',
    maxAge: 60 * 10, // 10 min
  });
}

// Use in Server Components and middleware (reads from the request cookie store)
export async function getSession() {
  const store = await cookies();
  const raw = store.get(COOKIE_NAME)?.value;
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export async function getPkceCookie() {
  const store = await cookies();
  const raw = store.get(PKCE_COOKIE)?.value;
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}
