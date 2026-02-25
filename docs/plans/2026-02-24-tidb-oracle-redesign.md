# TiDB Oracle Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild the TiDB Oracle UI with a Claude Code-inspired dark terminal aesthetic, ChatGPT OAuth PKCE login, and persona-switched navigation (Sales Rep / SE / Marketing / Admin).

**Architecture:** Next.js App Router with route groups — `(auth)` for public pages, `(app)` for protected pages behind a session cookie. Auth uses a custom `server.js` that runs both port 3000 (Next.js) and port 1455 (OAuth callback receiver), then hands off to a Next.js API route for token exchange. The Python backend is unchanged except for one new `/auth/validate` endpoint and passing OAuth tokens per-request to LLMService.

**Tech Stack:** Next.js 14 App Router, native Node crypto (PKCE), httpOnly cookies (no extra deps), Python FastAPI (existing), OpenAI SDK (existing)

---

## Critical context before starting

- **Client ID**: `app_EMoamEEZ73f0CkXaXp7hrann` (OpenAI Codex public client — do not change)
- **Auth URL**: `https://auth.openai.com/oauth/authorize`
- **Token URL**: `https://auth.openai.com/oauth/token`
- **Redirect URI**: MUST be exactly `http://localhost:1455/auth/callback` (registered by OpenAI)
- **Scopes**: `openid profile email offline_access`
- **Extra params**: `id_token_add_organizations=true&codex_cli_simplified_flow=true`
- The port 1455 server just captures the callback and redirects to `http://localhost:3000/api/auth/exchange?code=...&state=...`
- `code_verifier` is stored in a short-lived httpOnly cookie set before the redirect, read during exchange
- Session cookie name: `oracle_session` — contains `{ access_token, email, name, expires_at }`

---

## Task 1: Custom Next.js server (dual port 3000 + 1455)

**Files:**
- Create: `ui/server.js`
- Modify: `ui/package.json`

**Step 1: Create `ui/server.js`**

```js
const { createServer } = require('http');
const { parse } = require('url');
const next = require('next');

const dev = process.env.NODE_ENV !== 'production';
const app = next({ dev });
const handle = app.getRequestHandler();

app.prepare().then(() => {
  createServer((req, res) => {
    const parsedUrl = parse(req.url, true);
    handle(req, res, parsedUrl);
  }).listen(3000, '0.0.0.0', () => {
    console.log('> Next.js ready on http://localhost:3000');
  });

  createServer((req, res) => {
    const { pathname, query } = parse(req.url, true);
    if (pathname === '/auth/callback') {
      const code = query.code || '';
      const state = query.state || '';
      const target = `http://localhost:3000/api/auth/exchange?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`;
      res.writeHead(302, { Location: target });
      res.end();
    } else {
      res.writeHead(404);
      res.end('Not found');
    }
  }).listen(1455, '0.0.0.0', () => {
    console.log('> OAuth callback receiver ready on http://localhost:1455');
  });
});
```

**Step 2: Update `ui/package.json` scripts**

Change `"dev"` to use `server.js` instead of `next dev`. Replace the scripts block:

```json
"scripts": {
  "dev": "node server.js",
  "build": "next build",
  "start": "NODE_ENV=production node server.js"
}
```

**Step 3: Verify it starts**

```bash
cd ui && npm run dev
```

Expected: Two lines in console — `Next.js ready on http://localhost:3000` and `OAuth callback receiver ready on http://localhost:1455`. No errors.

**Step 4: Commit**

```bash
git add ui/server.js ui/package.json
git commit -m "feat: custom Next.js server with dual-port OAuth callback receiver (3000+1455)"
```

---

## Task 2: PKCE helpers and session utilities

**Files:**
- Create: `ui/lib/pkce.js`
- Create: `ui/lib/session.js`

**Step 1: Create `ui/lib/pkce.js`**

```js
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
  // JWT decode (no verification — this is a demo; in prod verify with JWKS)
  const parts = idToken.split('.');
  if (parts.length < 2) return {};
  try {
    return JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8'));
  } catch {
    return {};
  }
}
```

**Step 2: Create `ui/lib/session.js`**

```js
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
```

**Step 3: Commit**

```bash
git add ui/lib/pkce.js ui/lib/session.js
git commit -m "feat: PKCE helpers and session cookie utilities"
```

---

## Task 3: Auth API routes

**Files:**
- Create: `ui/app/api/auth/start/route.js`
- Create: `ui/app/api/auth/exchange/route.js`
- Create: `ui/app/api/auth/logout/route.js`
- Create: `ui/app/api/auth/me/route.js`

**Step 1: Create `ui/app/api/auth/start/route.js`**

```js
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
```

**Step 2: Create `ui/app/api/auth/exchange/route.js`**

```js
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
    return NextResponse.redirect(new URL(`/login?error=exchange_failed`, request.url));
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
```

**Step 3: Create `ui/app/api/auth/logout/route.js`**

```js
import { NextResponse } from 'next/server';

export async function POST() {
  const res = NextResponse.redirect(new URL('/login', 'http://localhost:3000'));
  res.cookies.set('oracle_session', '', { httpOnly: true, path: '/', maxAge: 0 });
  return res;
}
```

**Step 4: Create `ui/app/api/auth/me/route.js`**

```js
import { NextResponse } from 'next/server';
import { getSession } from '../../../../lib/session';

export async function GET() {
  const session = await getSession();
  if (!session) return NextResponse.json({ error: 'unauthenticated' }, { status: 401 });
  return NextResponse.json({ email: session.email, name: session.name, expires_at: session.expires_at });
}
```

**Step 5: Commit**

```bash
git add ui/app/api/auth/
git commit -m "feat: OAuth API routes — start, exchange, logout, me"
```

---

## Task 4: Middleware (protect /rep, /se, /marketing, /admin, /settings)

**Files:**
- Create: `ui/middleware.js`

**Step 1: Create `ui/middleware.js`**

```js
import { NextResponse } from 'next/server';

const PROTECTED = ['/rep', '/se', '/marketing', '/admin', '/settings'];

export function middleware(request) {
  const { pathname } = request.nextUrl;

  const isProtected = PROTECTED.some((p) => pathname.startsWith(p));
  if (!isProtected) return NextResponse.next();

  const session = request.cookies.get('oracle_session')?.value;
  if (!session) {
    return NextResponse.redirect(new URL('/login', request.url));
  }

  try {
    const parsed = JSON.parse(session);
    if (!parsed.access_token || Date.now() > parsed.expires_at) {
      return NextResponse.redirect(new URL('/login?error=expired', request.url));
    }
  } catch {
    return NextResponse.redirect(new URL('/login', request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/rep/:path*', '/se/:path*', '/marketing/:path*', '/admin/:path*', '/settings/:path*'],
};
```

**Step 2: Commit**

```bash
git add ui/middleware.js
git commit -m "feat: middleware to protect app routes, redirect to /login if unauthenticated"
```

---

## Task 5: New global CSS — Claude Code dark terminal theme

**Files:**
- Overwrite: `ui/app/globals.css`

**Step 1: Replace the entire contents of `ui/app/globals.css`**

```css
@import url('https://fonts.googleapis.com/css2?family=Geist+Mono:wght@400;500;600;700&display=swap');

:root {
  --bg:          #0a0a0a;
  --bg-2:        #111111;
  --panel:       #161616;
  --panel-hover: #1c1c1c;
  --border:      #242424;
  --border-mid:  #2e2e2e;
  --border-hi:   #3a3a3a;
  --text:        #e5e5e5;
  --text-2:      #999999;
  --text-3:      #555555;
  --accent:      #f97316;
  --accent-dim:  rgba(249,115,22,0.15);
  --accent-2:    #fb923c;
  --success:     #22c55e;
  --danger:      #ef4444;
  --font:        'Geist Mono', 'JetBrains Mono', 'Fira Code', ui-monospace, monospace;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body { height: 100%; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font);
  font-size: 13px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }

/* ── Shell layout ── */
.shell {
  display: grid;
  grid-template-columns: 200px 1fr;
  min-height: 100vh;
}

/* ── Sidebar ── */
.sidebar {
  background: var(--bg-2);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 0;
  position: sticky;
  top: 0;
  height: 100vh;
  overflow-y: auto;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 1rem 0.85rem 0.75rem;
  border-bottom: 1px solid var(--border);
}

.sidebar-brand-name {
  font-size: 0.85rem;
  font-weight: 700;
  color: var(--text);
  letter-spacing: -0.01em;
}

.sidebar-brand-sub {
  font-size: 0.7rem;
  color: var(--text-3);
  margin-top: 0.1rem;
}

.sidebar-nav {
  flex: 1;
  padding: 0.5rem 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sidebar-section-label {
  font-size: 0.65rem;
  font-weight: 600;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 0.6rem 0.4rem 0.25rem;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  padding: 0.45rem 0.55rem;
  border-radius: 4px;
  color: var(--text-2);
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  background: transparent;
  text-decoration: none;
  width: 100%;
  text-align: left;
  font-family: var(--font);
  transition: color 0.1s, background 0.1s;
}

.nav-link:hover {
  color: var(--text);
  background: var(--panel);
  text-decoration: none;
}

.nav-link.active {
  color: var(--accent);
  background: var(--accent-dim);
  border-color: rgba(249,115,22,0.2);
  font-weight: 600;
}

.nav-link-icon {
  width: 14px;
  text-align: center;
  flex-shrink: 0;
  opacity: 0.7;
}

.nav-link.active .nav-link-icon {
  opacity: 1;
}

.sidebar-footer {
  border-top: 1px solid var(--border);
  padding: 0.6rem 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.user-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0.5rem;
  border-radius: 4px;
}

.user-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--success);
  flex-shrink: 0;
}

.user-email {
  font-size: 0.72rem;
  color: var(--text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Main content ── */
.main {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  overflow: auto;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1.25rem;
  border-bottom: 1px solid var(--border);
  background: var(--bg);
  position: sticky;
  top: 0;
  z-index: 10;
}

.topbar-title {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text);
}

.topbar-meta {
  font-size: 0.72rem;
  color: var(--text-3);
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.content {
  padding: 1.25rem;
  display: grid;
  gap: 1rem;
  flex: 1;
}

/* ── Tags / pills ── */
.tag {
  display: inline-block;
  font-size: 0.68rem;
  font-weight: 600;
  padding: 0.12rem 0.45rem;
  border-radius: 3px;
  border: 1px solid var(--border-mid);
  color: var(--text-2);
  background: var(--panel);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.tag-orange {
  border-color: rgba(249,115,22,0.3);
  color: var(--accent);
  background: var(--accent-dim);
}

.tag-green {
  border-color: rgba(34,197,94,0.3);
  color: var(--success);
  background: rgba(34,197,94,0.1);
}

.tag-red {
  border-color: rgba(239,68,68,0.3);
  color: var(--danger);
  background: rgba(239,68,68,0.1);
}

/* ── Panels ── */
.panel {
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.65rem 0.85rem;
  border-bottom: 1px solid var(--border);
}

.panel-title {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text);
}

.panel-body {
  padding: 0.85rem;
}

/* ── KPI row ── */
.kpi-row {
  display: grid;
  gap: 0.75rem;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
}

.kpi-card {
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  padding: 0.65rem 0.75rem;
}

.kpi-label {
  font-size: 0.7rem;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.kpi-value {
  font-size: 1.45rem;
  font-weight: 700;
  color: var(--text);
  margin-top: 0.2rem;
  line-height: 1;
}

.kpi-sub {
  font-size: 0.7rem;
  color: var(--text-3);
  margin-top: 0.3rem;
}

/* ── Tables / lists ── */
.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th {
  font-size: 0.68rem;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 600;
  padding: 0.45rem 0.65rem;
  border-bottom: 1px solid var(--border);
  text-align: left;
}

.data-table td {
  padding: 0.55rem 0.65rem;
  font-size: 0.8rem;
  color: var(--text-2);
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}

.data-table tr:last-child td {
  border-bottom: 0;
}

.data-table tr:hover td {
  background: var(--panel-hover);
  color: var(--text);
}

.row-title {
  font-weight: 600;
  color: var(--text);
  font-size: 0.82rem;
}

/* ── Buttons ── */
.btn {
  border-radius: 4px;
  border: 1px solid var(--border-mid);
  background: var(--panel);
  color: var(--text-2);
  font-family: var(--font);
  font-size: 0.78rem;
  font-weight: 500;
  padding: 0.4rem 0.75rem;
  cursor: pointer;
  transition: color 0.1s, background 0.1s, border-color 0.1s;
}

.btn:hover {
  color: var(--text);
  background: var(--panel-hover);
  border-color: var(--border-hi);
}

.btn:disabled {
  opacity: 0.45;
  cursor: default;
}

.btn-primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
  font-weight: 600;
}

.btn-primary:hover:not(:disabled) {
  background: var(--accent-2);
  border-color: var(--accent-2);
}

.btn-ghost {
  background: transparent;
  border-color: transparent;
  color: var(--text-2);
}

.btn-ghost:hover {
  background: var(--panel);
  color: var(--text);
}

.btn-danger {
  border-color: rgba(239,68,68,0.4);
  color: var(--danger);
  background: rgba(239,68,68,0.08);
}

/* ── Form inputs ── */
.input {
  width: 100%;
  background: var(--bg);
  border: 1px solid var(--border-mid);
  border-radius: 4px;
  color: var(--text);
  font-family: var(--font);
  font-size: 0.82rem;
  padding: 0.5rem 0.65rem;
  outline: none;
  transition: border-color 0.1s;
}

.input:focus {
  border-color: var(--accent);
}

.input::placeholder {
  color: var(--text-3);
}

textarea.input {
  resize: vertical;
  min-height: 72px;
}

/* ── Answer / output box ── */
.answer-box {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0.75rem;
  margin-top: 0.65rem;
}

.answer-text {
  font-size: 0.82rem;
  color: var(--text);
  white-space: pre-wrap;
  line-height: 1.5;
}

.answer-citations {
  margin-top: 0.6rem;
  padding-top: 0.55rem;
  border-top: 1px solid var(--border);
}

.citation-label {
  font-size: 0.68rem;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 0.3rem;
}

.citation-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.citation-list li {
  font-size: 0.75rem;
  color: var(--text-3);
}

.citation-list li::before {
  content: '→ ';
  color: var(--accent);
}

/* ── Error / status ── */
.error-text {
  color: var(--danger);
  font-size: 0.78rem;
  margin-top: 0.4rem;
}

.status-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.75rem;
  color: var(--text-3);
}

/* ── Login page ── */
.login-shell {
  min-height: 100vh;
  display: grid;
  place-content: center;
  background: var(--bg);
}

.login-card {
  width: 360px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
  padding: 2rem;
}

.login-brand {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  margin-bottom: 1.5rem;
}

.login-brand-name {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--text);
}

.login-brand-sub {
  font-size: 0.75rem;
  color: var(--text-3);
}

.login-heading {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 0.35rem;
}

.login-sub {
  font-size: 0.78rem;
  color: var(--text-3);
  margin-bottom: 1.25rem;
  line-height: 1.5;
}

.login-btn-wrap {
  margin-top: 1rem;
}

.login-footer {
  margin-top: 1.25rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border);
  font-size: 0.7rem;
  color: var(--text-3);
  line-height: 1.5;
}

/* ── Two-column grid ── */
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

.three-col {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
}

/* ── Divider ── */
.divider {
  border: none;
  border-top: 1px solid var(--border);
  margin: 0.5rem 0;
}

/* ── Pre / code ── */
pre {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 0.75rem;
  color: var(--text-2);
  padding: 0.65rem;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

/* ── Responsive ── */
@media (max-width: 860px) {
  .shell { grid-template-columns: 1fr; }
  .sidebar { height: auto; position: static; flex-direction: row; flex-wrap: wrap; }
  .sidebar-nav { flex-direction: row; flex-wrap: wrap; }
  .two-col, .three-col { grid-template-columns: 1fr; }
}
```

**Step 2: Commit**

```bash
git add ui/app/globals.css
git commit -m "feat: Claude Code dark terminal theme — full CSS rewrite"
```

---

## Task 6: Root layout and root page (redirect)

**Files:**
- Overwrite: `ui/app/layout.js`
- Overwrite: `ui/app/page.js`

**Step 1: Update `ui/app/layout.js`**

```js
import './globals.css';

export const metadata = {
  title: 'TiDB Oracle',
  description: 'Internal GTM Copilot',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
```

**Step 2: Replace `ui/app/page.js`** (root redirect to /rep or /login)

```js
import { redirect } from 'next/navigation';
import { getSession } from '../lib/session';

export default async function RootPage() {
  const session = await getSession();
  if (session?.access_token && Date.now() < session.expires_at) {
    redirect('/rep');
  }
  redirect('/login');
}
```

**Step 3: Commit**

```bash
git add ui/app/layout.js ui/app/page.js
git commit -m "feat: root layout and redirect — authed users go to /rep, others to /login"
```

---

## Task 7: Login page

**Files:**
- Create: `ui/app/login/page.js`

**Step 1: Create `ui/app/login/page.js`**

```js
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
          Uses your ChatGPT Plus or Pro subscription — no separate API key needed.
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
          Internal only. Your ChatGPT session is used to power Oracle responses.
          Tokens are stored in a short-lived httpOnly cookie and never logged.
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add ui/app/login/
git commit -m "feat: login page with ChatGPT OAuth button"
```

---

## Task 8: App shell — shared layout with Sidebar

**Files:**
- Create: `ui/app/(app)/layout.js`
- Create: `ui/components/Sidebar.js`

**Step 1: Create `ui/components/Sidebar.js`**

```js
'use client';

import Link from 'next/link';
import Image from 'next/image';
import { usePathname } from 'next/navigation';
import { useState } from 'react';

const PERSONAS = [
  { href: '/rep',       label: 'Sales Rep',     icon: '◎' },
  { href: '/se',        label: 'Sales Engineer', icon: '⬡' },
  { href: '/marketing', label: 'Marketing',      icon: '◈' },
  { href: '/admin',     label: 'Admin',          icon: '⊞' },
];

const UTILITY = [
  { href: '/settings', label: 'Settings', icon: '⚙' },
];

export default function Sidebar({ email }) {
  const pathname = usePathname();
  const [loggingOut, setLoggingOut] = useState(false);

  const handleLogout = async () => {
    setLoggingOut(true);
    await fetch('/api/auth/logout', { method: 'POST' });
    window.location.href = '/login';
  };

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <Image alt="TiDB" src="/tidb-logo.png" width={22} height={22} />
        <div>
          <div className="sidebar-brand-name">TiDB Oracle</div>
          <div className="sidebar-brand-sub">GTM Copilot</div>
        </div>
      </div>

      <nav className="sidebar-nav">
        <div className="sidebar-section-label">Persona</div>
        {PERSONAS.map(({ href, label, icon }) => (
          <Link
            key={href}
            href={href}
            className={`nav-link${pathname.startsWith(href) ? ' active' : ''}`}
          >
            <span className="nav-link-icon">{icon}</span>
            {label}
          </Link>
        ))}

        <div className="sidebar-section-label" style={{ marginTop: '0.5rem' }}>Account</div>
        {UTILITY.map(({ href, label, icon }) => (
          <Link
            key={href}
            href={href}
            className={`nav-link${pathname.startsWith(href) ? ' active' : ''}`}
          >
            <span className="nav-link-icon">{icon}</span>
            {label}
          </Link>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className="user-row">
          <div className="user-dot" />
          <div className="user-email">{email}</div>
        </div>
        <button
          className="nav-link btn-ghost"
          onClick={handleLogout}
          disabled={loggingOut}
          style={{ width: '100%' }}
        >
          <span className="nav-link-icon">→</span>
          {loggingOut ? 'Signing out...' : 'Sign out'}
        </button>
      </div>
    </aside>
  );
}
```

**Step 2: Create `ui/app/(app)/layout.js`**

```js
import { redirect } from 'next/navigation';
import { getSession } from '../../lib/session';
import Sidebar from '../../components/Sidebar';

export default async function AppLayout({ children }) {
  const session = await getSession();
  if (!session?.access_token) redirect('/login');

  return (
    <div className="shell">
      <Sidebar email={session.email} />
      <div className="main">{children}</div>
    </div>
  );
}
```

**Step 3: Commit**

```bash
git add ui/components/Sidebar.js ui/app/\(app\)/layout.js
git commit -m "feat: app shell — sidebar with persona switcher and session-aware layout"
```

---

## Task 9: Update api.js to pass session token to backend

**Files:**
- Overwrite: `ui/lib/api.js`

**Step 1: Replace `ui/lib/api.js`**

```js
function getApiBase() {
  if (typeof window === 'undefined') {
    return process.env.API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
  }
  return process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
}

function getSessionToken() {
  if (typeof document === 'undefined') return null;
  // Read from cookie (not httpOnly ones — the access_token is NOT exposed client-side)
  // Instead, backend routes read from the httpOnly cookie via SSR.
  // For client-side calls we POST to our own /api/* proxy routes.
  return null;
}

export async function apiGet(path) {
  const res = await fetch(`${getApiBase()}${path}`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json();
}

export async function apiPost(path, body) {
  const res = await fetch(`${getApiBase()}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    cache: 'no-store',
  });
  if (!res.ok) {
    const msg = await res.text();
    throw new Error(`API ${path} failed: ${res.status} ${msg}`);
  }
  return res.json();
}

// For client components — calls Next.js proxy API routes that inject the token server-side
export async function proxyPost(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const msg = await res.text();
    throw new Error(`Proxy ${path} failed: ${res.status} ${msg}`);
  }
  return res.json();
}
```

**Step 2: Create the proxy route `ui/app/api/oracle/route.js`** (server-side, injects token)

```js
import { NextResponse } from 'next/server';
import { getSession } from '../../../lib/session';

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000';

export async function POST(request) {
  const session = await getSession();
  if (!session?.access_token) {
    return NextResponse.json({ error: 'unauthenticated' }, { status: 401 });
  }

  const body = await request.json();
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-OpenAI-Token': session.access_token,
    },
    body: JSON.stringify({ ...body, user: session.email }),
  });

  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
```

**Step 3: Commit**

```bash
git add ui/lib/api.js ui/app/api/oracle/route.js
git commit -m "feat: api.js update + server-side oracle proxy route that injects session token"
```

---

## Task 10: Backend — accept per-request OpenAI token

**Files:**
- Modify: `api/app/services/llm.py`
- Modify: `api/app/api/routes/chat.py`
- Modify: `api/app/schemas/chat.py` (if needed)

**Step 1: Read `api/app/schemas/chat.py`** first to understand ChatRequest

```bash
cat api/app/schemas/chat.py
```

**Step 2: Add `openai_token` field to ChatRequest if not present**

In `api/app/schemas/chat.py`, add the optional field:

```python
class ChatRequest(BaseModel):
    mode: str = "oracle"
    user: str = "anonymous"
    message: str
    top_k: int = 8
    filters: FilterSpec = FilterSpec()
    context: ContextSpec = ContextSpec()
    openai_token: str | None = None  # add this
```

**Step 3: Modify `api/app/services/llm.py`** — accept optional per-request key

In `LLMService.__init__`, make `api_key` a parameter:

```python
class LLMService:
    def __init__(self, api_key: str | None = None) -> None:
        self.settings = get_settings()
        self.model = self.settings.openai_model
        self._validate_enterprise_settings()
        effective_key = api_key or self.settings.openai_api_key
        if effective_key:
            self.client = OpenAI(api_key=effective_key, base_url=self.settings.openai_base_url)
        else:
            self.client = None
            if self.settings.security_fail_closed_on_missing_llm_key:
                raise RuntimeError("OPENAI_API_KEY is required by security policy for LLM calls.")
```

**Step 4: Modify `api/app/api/routes/chat.py`** — extract token from header and pass to orchestrator

```python
from fastapi import APIRouter, Depends, Request

@router.post("")
def chat(req: ChatRequest, request: Request, db: Session = Depends(db_session)) -> dict:
    openai_token = request.headers.get("X-OpenAI-Token") or req.openai_token
    orchestrator = ChatOrchestrator(db, openai_token=openai_token)
    # rest unchanged
```

**Step 5: Modify `ChatOrchestrator`** — pass token to LLMService

Read `api/app/services/chat_orchestrator.py` first, then update its `__init__` to accept and pass through the token to `LLMService`.

**Step 6: Commit**

```bash
git add api/app/schemas/ api/app/services/llm.py api/app/api/routes/chat.py api/app/services/chat_orchestrator.py
git commit -m "feat: backend accepts X-OpenAI-Token header for per-request ChatGPT OAuth key"
```

---

## Task 11: Fake call transcripts data

**Files:**
- Create: `ui/data/fake-calls.js`

**Step 1: Create `ui/data/fake-calls.js`**

```js
export const FAKE_CALLS = [
  {
    id: 'call_12345',
    account: 'Evernorth',
    date: '2026-02-17',
    stage: 'Technical Validation',
    rep: 'Estyn C.',
    repEmail: 'estyn.c@pingcap.com',
    se: 'Jordan R.',
    seEmail: 'jordan.r@pingcap.com',
    value: '$1.2M',
    summary: 'Customer expects 40–50 TB growth over 18 months with frequent schema changes. They are running SingleStore today and benchmarked compression at 3x. They asked about TiFlash query latency for their analytics workload and online DDL behavior during peak traffic windows.',
    risks: [
      'SingleStore compression claim needs a direct TiFlash counter-benchmark',
      'ETL window and DDL tolerance not confirmed before POC scope freeze',
      'p95 analytics latency target not defined',
    ],
    nextSteps: [
      'Send TiFlash sizing worksheet with compression assumptions',
      'Confirm ETL window with data engineering team',
      'Schedule schema design review with SE before POC kickoff',
    ],
    questions: [
      'What is your current p95/p99 latency target for the analytics queries?',
      'How frequently do schema changes happen in production and during what windows?',
      'What is the expected ingest rate at peak?',
    ],
    competitors: ['SingleStore'],
    collateral: ['TiFlash Sizing FAQ', 'Online DDL Objection Handling', 'TiDB vs SingleStore Compression Brief'],
    transcript: `[00:02] Rep: Thanks for joining. Quick agenda — we want to walk through your growth projections and get alignment on what a POC would look like.\n[00:45] Champion: Sure. We're at about 12 TB today, expecting 40-50 TB in 18 months. Schema changes are weekly in some services.\n[02:10] Rep: And SingleStore — is that the primary comparison?\n[02:18] Champion: Yes. We benchmarked their compression at roughly 3x. That matters a lot for our storage costs.\n[04:33] SE: TiFlash uses columnar storage and we typically see 4-8x depending on data type distribution. We can run a direct comparison.\n[06:12] Champion: What about online DDL? We had a painful migration last year — 6 hours of downtime.\n[06:40] SE: TiDB handles most DDL changes online with zero downtime. There are edge cases for large column type changes, but we can scope those in the POC.\n[09:55] Champion: That's promising. Let's schedule a deeper technical session.`,
  },
  {
    id: 'call_67890',
    account: 'Northwind Health',
    date: '2026-02-18',
    stage: 'POC Design',
    rep: 'Maya T.',
    repEmail: 'maya.t@pingcap.com',
    se: 'Priya N.',
    seEmail: 'priya.n@pingcap.com',
    value: '$820K',
    summary: 'Champion asked about HTAP rollout sequence and replication lag between TiKV and TiFlash. POC scope is converging around 5 core queries with p95 < 200ms SLA. Procurement asked about HIPAA BAA availability for TiDB Cloud Dedicated.',
    risks: [
      'Unclear p95 query latency target — champion said "under 200ms" but no formal SLA doc',
      'HIPAA BAA status for TiDB Cloud Dedicated not confirmed',
      'Phased HTAP adoption plan not prepared yet',
    ],
    nextSteps: [
      'Prepare phased TiFlash adoption plan with capacity assumptions',
      'Confirm HIPAA BAA availability with legal/sales ops',
      'Collect top 10 queries with current latency baselines',
    ],
    questions: [
      'Is the p95 < 200ms target formal or informal at this point?',
      'Which HIPAA workloads will run on TiDB first — OLTP or analytics?',
      'What is the replication lag tolerance for the analytics replica?',
    ],
    competitors: ['Snowflake', 'Aurora'],
    collateral: ['TiDB Cloud HIPAA Compliance Brief', 'HTAP Architecture Guide', 'TiFlash Replication Lag FAQ'],
    transcript: `[00:05] Champion: We looked at your HTAP docs. Big question — how do we sequence the rollout? Do we put OLTP on TiKV first, then enable TiFlash later?\n[01:12] SE: Exactly right. You run OLTP on TiKV and can enable TiFlash async replication without any application changes. Typical lag is under 5 seconds.\n[02:45] Champion: Five seconds is fine for our batch reports. What about real-time dashboards?\n[03:10] SE: For real-time you can tune the replication interval. We've gotten to sub-second in some configurations. Let's put your top 5 queries into the POC.\n[05:30] Rep: Quick question from procurement — do you have a HIPAA BAA for Cloud Dedicated?\n[05:45] SE: Yes, TiDB Cloud Dedicated supports HIPAA workloads. I'll confirm the BAA process and connect you with our compliance team.\n[08:20] Champion: Let's target p95 under 200ms for the POC queries. That's our informal bar.`,
  },
  {
    id: 'call_99881',
    account: 'Summit Retail',
    date: '2026-02-19',
    stage: 'Business Case',
    rep: 'Jordan R.',
    repEmail: 'jordan.r@pingcap.com',
    se: null,
    seEmail: null,
    value: '$640K',
    summary: 'Economic buyer requested full TCO visibility vs current MySQL + Redshift stack. They want a 12-month migration milestones view and a clear cost narrative. No technical objections — this is now a procurement and executive buy-in conversation.',
    risks: [
      'Cost narrative not finalized — economic buyer needs numbers before next QBR',
      'No SE on this call — technical assumptions in ROI model unvalidated',
      'Migration timeline risk not quantified',
    ],
    nextSteps: [
      'Build 12-month TCO model comparing MySQL+Redshift vs TiDB Cloud',
      'Create ROI framing deck for economic buyer',
      'Add SE to next call to validate architecture assumptions in cost model',
    ],
    questions: [
      'What is the current annual spend on MySQL licensing, Redshift, and ops?',
      'What is the acceptable migration window — can you run parallel systems?',
      'Who else needs to sign off before contract — is legal involved?',
    ],
    competitors: ['MySQL', 'Redshift'],
    collateral: ['TiDB TCO Calculator', 'MySQL + Redshift vs TiDB Cloud Brief', 'Migration Playbook'],
    transcript: `[00:10] Economic Buyer: I need to understand total cost. Right now we're paying for MySQL Enterprise, Redshift, and two DBAs who spend 60% of their time on this stack.\n[01:45] Rep: We can model that directly. Typical customers replacing a similar stack see 30-40% TCO reduction in year one once you factor in consolidation.\n[03:20] Economic Buyer: I need specific numbers, not typical. Can you build a model with our actual usage?\n[03:35] Rep: Absolutely. I'll need your current Redshift node count, MySQL instance size, and rough data volume.\n[05:00] Economic Buyer: I'll have my team send that over. What does a 12-month migration look like?\n[05:30] Rep: We usually phase it — OLTP first, analytics consolidation in months 4-6, full cutover by month 9. I'll put together a milestone view.\n[07:10] Economic Buyer: Good. Get me something I can take to the CFO.`,
  },
];

export const FAKE_PRIORITIES = FAKE_CALLS.map((c) => ({
  account: c.account,
  owner: c.rep,
  stage: c.stage,
  value: c.value,
  risk: c.risks[0],
  action: c.nextSteps[0],
}));

export const FAKE_COACHING = FAKE_CALLS.map((c) => ({
  account: c.account,
  happened: c.summary,
  next: c.nextSteps[0],
}));
```

**Step 2: Commit**

```bash
git add ui/data/fake-calls.js
git commit -m "feat: fake call transcripts — Evernorth, Northwind Health, Summit Retail"
```

---

## Task 12: Sales Rep persona page

**Files:**
- Create: `ui/app/(app)/rep/page.js`
- Update: `ui/components/AskOracleWidget.js`

**Step 1: Create `ui/app/(app)/rep/page.js`**

```js
import { FAKE_PRIORITIES, FAKE_COACHING, FAKE_CALLS } from '../../../data/fake-calls';
import AskOracleWidget from '../../../components/AskOracleWidget';
import Link from 'next/link';

export default function RepPage() {
  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">Sales Rep</div>
          <div className="topbar-meta">Deal priorities · call coaching · follow-ups</div>
        </div>
        <div className="topbar-right">
          <span className="tag tag-orange">3 active deals</span>
          <span className="tag">Sample data</span>
        </div>
      </div>

      <div className="content">
        {/* KPIs */}
        <div className="kpi-row">
          {[
            { label: 'Deals in Motion', value: '3', sub: 'Technical Validation → Business Case' },
            { label: 'Open Follow-Ups', value: '7', sub: '3 past due' },
            { label: 'Risk Flags', value: '3', sub: 'All high-priority accounts' },
          ].map((k) => (
            <div className="kpi-card" key={k.label}>
              <div className="kpi-label">{k.label}</div>
              <div className="kpi-value">{k.value}</div>
              <div className="kpi-sub">{k.sub}</div>
            </div>
          ))}
        </div>

        <div className="two-col">
          {/* Deal Priorities */}
          <div className="panel">
            <div className="panel-header">
              <span className="panel-title">Deal Priorities</span>
              <span className="tag">Top 3</span>
            </div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Stage</th>
                  <th>Value</th>
                  <th>Risk</th>
                </tr>
              </thead>
              <tbody>
                {FAKE_PRIORITIES.map((d) => (
                  <tr key={d.account}>
                    <td className="row-title">{d.account}</td>
                    <td>{d.stage}</td>
                    <td style={{ color: 'var(--accent)' }}>{d.value}</td>
                    <td style={{ color: 'var(--danger)', fontSize: '0.75rem' }}>{d.risk}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Call Coaching */}
          <div className="panel">
            <div className="panel-header">
              <span className="panel-title">Call Coaching</span>
              <span className="tag tag-green">Fresh</span>
            </div>
            <div className="panel-body" style={{ display: 'grid', gap: '0.75rem' }}>
              {FAKE_COACHING.map((item) => (
                <div key={item.account} style={{ borderBottom: '1px solid var(--border)', paddingBottom: '0.65rem' }}>
                  <div className="row-title" style={{ marginBottom: '0.3rem' }}>{item.account}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-2)', marginBottom: '0.25rem' }}>{item.happened}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--accent)' }}>→ {item.next}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Recent Calls */}
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">Recent Calls</span>
            <span className="tag">{FAKE_CALLS.length} indexed</span>
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Account</th>
                <th>Date</th>
                <th>Rep</th>
                <th>Stage</th>
                <th>Next Action</th>
              </tr>
            </thead>
            <tbody>
              {FAKE_CALLS.map((c) => (
                <tr key={c.id}>
                  <td>
                    <Link href={`/calls/${c.id}`} className="row-title" style={{ color: 'var(--accent)' }}>
                      {c.account}
                    </Link>
                  </td>
                  <td>{c.date}</td>
                  <td>{c.rep}</td>
                  <td>{c.stage}</td>
                  <td style={{ fontSize: '0.75rem' }}>{c.nextSteps[0]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Ask Oracle */}
        <AskOracleWidget defaultQuestion="How should we position TiDB vs SingleStore for a 40TB analytics workload?" />
      </div>
    </>
  );
}
```

**Step 2: Rewrite `ui/components/AskOracleWidget.js`** with new styles

```js
'use client';

import { useState } from 'react';

export default function AskOracleWidget({ defaultQuestion = '' }) {
  const [question, setQuestion] = useState(defaultQuestion);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [answer, setAnswer] = useState('');
  const [citations, setCitations] = useState([]);

  const onAsk = async () => {
    const q = question.trim();
    if (q.length < 2) { setError('Enter a question.'); return; }
    setLoading(true);
    setError('');
    setAnswer('');
    setCitations([]);
    try {
      const res = await fetch('/api/oracle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'oracle', message: q, top_k: 8 }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setAnswer(data.answer || 'No answer returned.');
      setCitations(data.citations || []);
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Ask Oracle</span>
        <span className="tag tag-orange">Live</span>
      </div>
      <div className="panel-body" style={{ display: 'grid', gap: '0.65rem' }}>
        <textarea
          className="input"
          rows={3}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask any GTM or technical question..."
        />
        <div>
          <button className="btn btn-primary" onClick={onAsk} disabled={loading}>
            {loading ? 'Thinking...' : 'Ask Oracle →'}
          </button>
        </div>
        {error && <p className="error-text">{error}</p>}
        {answer && (
          <div className="answer-box">
            <p className="answer-text">{answer}</p>
            {citations.length > 0 && (
              <div className="answer-citations">
                <div className="citation-label">Evidence</div>
                <ul className="citation-list">
                  {citations.slice(0, 5).map((c) => (
                    <li key={`${c.source_id}-${c.chunk_id}`}>{c.title} ({c.source_id})</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
```

**Step 3: Commit**

```bash
git add ui/app/\(app\)/rep/ ui/components/AskOracleWidget.js
git commit -m "feat: Sales Rep persona page with deals, coaching, call list, Ask Oracle"
```

---

## Task 13: Sales Engineer persona page

**Files:**
- Create: `ui/app/(app)/se/page.js`

**Step 1: Create `ui/app/(app)/se/page.js`**

```js
import { FAKE_CALLS } from '../../../data/fake-calls';
import AskOracleWidget from '../../../components/AskOracleWidget';

const TRACKS = [
  { label: 'TiDB X Assets', desc: 'Benchmark worksheet + architecture one-pager' },
  { label: 'TiDB Cloud Dedicated', desc: 'Deployment checklist + security FAQ pack' },
  { label: 'HTAP Architecture', desc: 'TiKV + TiFlash phased rollout guide' },
  { label: 'POC Scorecard', desc: 'Success criteria template + measurement rubric' },
];

export default function SEPage() {
  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">Sales Engineer</div>
          <div className="topbar-meta">Technical assets · POC planning · architecture guidance</div>
        </div>
        <div className="topbar-right">
          <span className="tag tag-orange">3 active POCs</span>
        </div>
      </div>

      <div className="content">
        <div className="kpi-row">
          {[
            { label: 'Active POCs', value: '3', sub: 'Evernorth · Northwind · Summit' },
            { label: 'Assets Generated', value: '12', sub: 'This month' },
            { label: 'Avg POC Duration', value: '18d', sub: 'vs 24d last quarter' },
          ].map((k) => (
            <div className="kpi-card" key={k.label}>
              <div className="kpi-label">{k.label}</div>
              <div className="kpi-value">{k.value}</div>
              <div className="kpi-sub">{k.sub}</div>
            </div>
          ))}
        </div>

        <div className="two-col">
          {/* Technical asset generator */}
          <div className="panel">
            <div className="panel-header">
              <span className="panel-title">Asset Generator</span>
              <span className="tag">4 tracks</span>
            </div>
            <div className="panel-body" style={{ display: 'grid', gap: '0.5rem' }}>
              {TRACKS.map((t) => (
                <div key={t.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.5rem 0', borderBottom: '1px solid var(--border)' }}>
                  <div>
                    <div className="row-title" style={{ fontSize: '0.8rem' }}>{t.label}</div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-3)', marginTop: '0.15rem' }}>{t.desc}</div>
                  </div>
                  <button className="btn" style={{ flexShrink: 0, marginLeft: '0.75rem' }}>Generate</button>
                </div>
              ))}
            </div>
          </div>

          {/* POC planning */}
          <div className="panel">
            <div className="panel-header">
              <span className="panel-title">POC Status</span>
            </div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Stage</th>
                  <th>Key Risk</th>
                </tr>
              </thead>
              <tbody>
                {FAKE_CALLS.map((c) => (
                  <tr key={c.id}>
                    <td className="row-title">{c.account}</td>
                    <td>{c.stage}</td>
                    <td style={{ fontSize: '0.75rem', color: 'var(--danger)' }}>{c.risks[0]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Discovery questions by account */}
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">Discovery Questions</span>
            <span className="tag">From latest calls</span>
          </div>
          <div className="panel-body" style={{ display: 'grid', gap: '0.85rem' }}>
            {FAKE_CALLS.map((c) => (
              <div key={c.id}>
                <div className="row-title" style={{ marginBottom: '0.35rem' }}>{c.account}</div>
                <ul style={{ listStyle: 'none', display: 'grid', gap: '0.25rem' }}>
                  {c.questions.map((q) => (
                    <li key={q} style={{ fontSize: '0.78rem', color: 'var(--text-2)' }}>
                      <span style={{ color: 'var(--accent)' }}>?  </span>{q}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>

        <AskOracleWidget defaultQuestion="What are the TiFlash replication lag characteristics for a 10TB HTAP workload?" />
      </div>
    </>
  );
}
```

**Step 2: Commit**

```bash
git add ui/app/\(app\)/se/
git commit -m "feat: Sales Engineer persona page with asset generator, POC status, discovery questions"
```

---

## Task 14: Marketing persona page

**Files:**
- Create: `ui/app/(app)/marketing/page.js`

**Step 1: Create `ui/app/(app)/marketing/page.js`**

```js
'use client';

import { useState } from 'react';
import AskOracleWidget from '../../../components/AskOracleWidget';

const CAMPAIGNS = [
  { label: 'ABM Target List', desc: 'Build from intent signals + ICP criteria', status: 'ready' },
  { label: 'Outbound Email Sequence', desc: '3-touch sequence for financial services ICP', status: 'ready' },
  { label: 'LinkedIn Connection Copy', desc: 'Connection request + follow-up message pair', status: 'ready' },
  { label: 'Webinar Invite', desc: 'HTAP + real-time analytics webinar invite', status: 'ready' },
];

const METRICS = [
  { label: 'Target Accounts', value: '42' },
  { label: 'Open Opportunities', value: '13' },
  { label: 'New Leads (7d)', value: '26' },
  { label: 'Content Assets', value: '8' },
];

export default function MarketingPage() {
  const [log, setLog] = useState([]);

  const launch = (label) => {
    setLog((prev) => [`[${new Date().toLocaleTimeString()}] ${label} — launched`, ...prev].slice(0, 10));
  };

  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">Marketing</div>
          <div className="topbar-meta">ABM · outreach · content generation</div>
        </div>
        <div className="topbar-right">
          <span className="tag tag-orange">Auto-pilot</span>
        </div>
      </div>

      <div className="content">
        <div className="kpi-row">
          {METRICS.map((m) => (
            <div className="kpi-card" key={m.label}>
              <div className="kpi-label">{m.label}</div>
              <div className="kpi-value">{m.value}</div>
            </div>
          ))}
        </div>

        <div className="two-col">
          <div className="panel">
            <div className="panel-header">
              <span className="panel-title">Campaign Actions</span>
            </div>
            <div className="panel-body" style={{ display: 'grid', gap: '0.5rem' }}>
              {CAMPAIGNS.map((c) => (
                <div key={c.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.5rem 0', borderBottom: '1px solid var(--border)' }}>
                  <div>
                    <div className="row-title" style={{ fontSize: '0.8rem' }}>{c.label}</div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-3)', marginTop: '0.15rem' }}>{c.desc}</div>
                  </div>
                  <button className="btn" onClick={() => launch(c.label)} style={{ flexShrink: 0, marginLeft: '0.75rem' }}>
                    Launch
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">
              <span className="panel-title">Automation Log</span>
            </div>
            <div className="panel-body">
              {log.length === 0 ? (
                <div style={{ color: 'var(--text-3)', fontSize: '0.78rem' }}>No campaigns launched yet.</div>
              ) : (
                <ul style={{ listStyle: 'none', display: 'grid', gap: '0.35rem' }}>
                  {log.map((entry) => (
                    <li key={entry} style={{ fontSize: '0.75rem', color: 'var(--text-2)', fontFamily: 'var(--font)' }}>
                      <span style={{ color: 'var(--success)' }}>✓ </span>{entry}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>

        <AskOracleWidget defaultQuestion="What are the key HTAP messaging points for financial services accounts replacing Redshift?" />
      </div>
    </>
  );
}
```

**Step 2: Commit**

```bash
git add ui/app/\(app\)/marketing/
git commit -m "feat: Marketing persona page with campaigns, metrics, Ask Oracle"
```

---

## Task 15: Admin persona page

**Files:**
- Create: `ui/app/(app)/admin/page.js`

**Step 1: Create `ui/app/(app)/admin/page.js`**

```js
import { apiGet } from '../../../lib/api';
import { FAKE_CALLS } from '../../../data/fake-calls';

const SAMPLE_AUDITS = [
  { id: '1', action: 'sync_drive', status: 'ok', actor: 'system', ts: '2026-02-19T10:02:00Z' },
  { id: '2', action: 'sync_chorus', status: 'ok', actor: 'system', ts: '2026-02-19T10:05:00Z' },
  { id: '3', action: 'chat', status: 'ok', actor: 'estyn.c@pingcap.com', ts: '2026-02-19T10:12:00Z' },
  { id: '4', action: 'draft_message', status: 'ok', actor: 'maya.t@pingcap.com', ts: '2026-02-19T11:01:00Z' },
  { id: '5', action: 'chat', status: 'error', actor: 'jordan.r@pingcap.com', ts: '2026-02-19T11:45:00Z' },
];

const SAMPLE_DOCS = [
  { title: 'TiDB GTM Positioning Playbook', source: 'google_drive', indexed: '2026-02-18' },
  { title: 'TiFlash Sizing FAQ', source: 'google_drive', indexed: '2026-02-18' },
  { title: 'Online DDL Objection Handling', source: 'google_drive', indexed: '2026-02-18' },
];

export default async function AdminPage() {
  const [docsRaw, auditsRaw] = await Promise.all([
    apiGet('/kb/documents?limit=30').catch(() => []),
    apiGet('/admin/audit?limit=30').catch(() => []),
  ]);

  const docs = docsRaw.length ? docsRaw : SAMPLE_DOCS;
  const audits = auditsRaw.length ? auditsRaw : SAMPLE_AUDITS;
  const sampleMode = !docsRaw.length;

  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">Admin</div>
          <div className="topbar-meta">Data coverage · audit log · sync status</div>
        </div>
        <div className="topbar-right">
          <span className={`tag ${sampleMode ? '' : 'tag-green'}`}>{sampleMode ? 'Sample data' : 'Live data'}</span>
        </div>
      </div>

      <div className="content">
        <div className="kpi-row">
          {[
            { label: 'Docs Indexed', value: docs.length, sub: docs[0]?.title || '—' },
            { label: 'Calls Indexed', value: FAKE_CALLS.length, sub: 'Evernorth · Northwind · Summit' },
            { label: 'Audit Events', value: audits.length, sub: 'Last 30 days' },
          ].map((k) => (
            <div className="kpi-card" key={k.label}>
              <div className="kpi-label">{k.label}</div>
              <div className="kpi-value">{k.value}</div>
              <div className="kpi-sub">{k.sub}</div>
            </div>
          ))}
        </div>

        <div className="two-col">
          <div className="panel">
            <div className="panel-header">
              <span className="panel-title">Knowledge Base</span>
              <span className="tag">{docs.length} docs</span>
            </div>
            <table className="data-table">
              <thead>
                <tr><th>Title</th><th>Source</th><th>Indexed</th></tr>
              </thead>
              <tbody>
                {docs.slice(0, 10).map((d, i) => (
                  <tr key={d.id || i}>
                    <td className="row-title">{d.title}</td>
                    <td style={{ color: 'var(--text-3)' }}>{d.source_type || d.source || '—'}</td>
                    <td style={{ color: 'var(--text-3)' }}>{d.indexed || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="panel">
            <div className="panel-header">
              <span className="panel-title">Audit Log</span>
            </div>
            <table className="data-table">
              <thead>
                <tr><th>Action</th><th>Actor</th><th>Status</th><th>Time</th></tr>
              </thead>
              <tbody>
                {audits.slice(0, 10).map((a) => (
                  <tr key={a.id}>
                    <td className="row-title">{a.action}</td>
                    <td style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>{a.actor || a.actor_email || '—'}</td>
                    <td>
                      <span className={`tag ${a.status === 'ok' ? 'tag-green' : 'tag-red'}`}>
                        {a.status}
                      </span>
                    </td>
                    <td style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>
                      {new Date(a.ts || a.timestamp || 0).toLocaleTimeString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
```

**Step 2: Commit**

```bash
git add ui/app/\(app\)/admin/
git commit -m "feat: Admin persona page with data coverage, KB, and audit log"
```

---

## Task 16: Settings page

**Files:**
- Create: `ui/app/(app)/settings/page.js`

**Step 1: Create `ui/app/(app)/settings/page.js`**

```js
import { getSession } from '../../../lib/session';

export default async function SettingsPage() {
  const session = await getSession();

  const expiresIn = session?.expires_at
    ? Math.max(0, Math.round((session.expires_at - Date.now()) / 1000 / 60))
    : 0;

  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">Settings</div>
          <div className="topbar-meta">Connected account · preferences · session</div>
        </div>
      </div>

      <div className="content">
        {/* Connected account */}
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">ChatGPT Account</span>
            <span className="tag tag-green">Connected</span>
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
              <span style={{ color: 'var(--text)' }}>ChatGPT OAuth PKCE</span>
              <span style={{ color: 'var(--text-3)' }}>Client ID</span>
              <span style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>app_EMoamEEZ73f0CkXaXp7hrann</span>
            </div>
            <form action="/api/auth/logout" method="POST" style={{ marginTop: '0.25rem' }}>
              <button type="submit" className="btn btn-danger">Sign out</button>
            </form>
          </div>
        </div>

        {/* LLM config */}
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">LLM Configuration</span>
          </div>
          <div className="panel-body" style={{ display: 'grid', gap: '0.5rem', fontSize: '0.82rem' }}>
            {[
              { label: 'Model', value: 'gpt-4.1-mini (via ChatGPT OAuth)' },
              { label: 'Embedding Model', value: 'text-embedding-3-small' },
              { label: 'Retrieval Top-K', value: '8' },
              { label: 'Redact before LLM', value: 'Enabled' },
            ].map(({ label, value }) => (
              <div key={label} style={{ display: 'grid', gridTemplateColumns: '160px 1fr', gap: '0.5rem' }}>
                <span style={{ color: 'var(--text-3)' }}>{label}</span>
                <span style={{ color: 'var(--text)' }}>{value}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Guardrails */}
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
```

**Step 2: Commit**

```bash
git add ui/app/\(app\)/settings/
git commit -m "feat: Settings page with connected ChatGPT account, session info, LLM config, guardrails"
```

---

## Task 17: Clean up call detail page

**Files:**
- Overwrite: `ui/app/calls/[id]/page.js`

**Step 1: Replace call detail page**

```js
import { FAKE_CALLS } from '../../../data/fake-calls';
import Link from 'next/link';

export default async function CallPage({ params }) {
  const { id } = await params;

  // Try fake data first (demo mode)
  const fakeCall = FAKE_CALLS.find((c) => c.id === id);

  if (!fakeCall) {
    return (
      <div className="content" style={{ padding: '2rem' }}>
        <p style={{ color: 'var(--text-3)' }}>Call not found: {id}</p>
        <Link href="/rep">← Back</Link>
      </div>
    );
  }

  return (
    <div style={{ padding: '1.25rem', display: 'grid', gap: '1rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <Link href="/rep" style={{ color: 'var(--text-3)', fontSize: '0.78rem' }}>← Back</Link>
        <span className="tag">{fakeCall.stage}</span>
        <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{fakeCall.value}</span>
      </div>

      <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text)' }}>
        {fakeCall.account} — {fakeCall.date}
      </div>

      <div className="two-col">
        <div className="panel">
          <div className="panel-header"><span className="panel-title">Call Summary</span></div>
          <div className="panel-body" style={{ fontSize: '0.82rem', color: 'var(--text-2)', lineHeight: 1.6 }}>
            {fakeCall.summary}
          </div>
        </div>

        <div className="panel">
          <div className="panel-header"><span className="panel-title">Metadata</span></div>
          <div className="panel-body" style={{ display: 'grid', gap: '0.4rem', fontSize: '0.8rem' }}>
            {[
              { label: 'Rep', value: `${fakeCall.rep} (${fakeCall.repEmail})` },
              { label: 'SE', value: fakeCall.se ? `${fakeCall.se} (${fakeCall.seEmail})` : 'None' },
              { label: 'Competitors', value: fakeCall.competitors.join(', ') },
            ].map(({ label, value }) => (
              <div key={label} style={{ display: 'grid', gridTemplateColumns: '90px 1fr' }}>
                <span style={{ color: 'var(--text-3)' }}>{label}</span>
                <span style={{ color: 'var(--text)' }}>{value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="three-col">
        <div className="panel">
          <div className="panel-header"><span className="panel-title">Risks</span></div>
          <div className="panel-body">
            <ul style={{ listStyle: 'none', display: 'grid', gap: '0.45rem' }}>
              {fakeCall.risks.map((r) => (
                <li key={r} style={{ fontSize: '0.78rem', color: 'var(--danger)' }}>⚠ {r}</li>
              ))}
            </ul>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header"><span className="panel-title">Next Steps</span></div>
          <div className="panel-body">
            <ul style={{ listStyle: 'none', display: 'grid', gap: '0.45rem' }}>
              {fakeCall.nextSteps.map((s) => (
                <li key={s} style={{ fontSize: '0.78rem', color: 'var(--text-2)' }}>→ {s}</li>
              ))}
            </ul>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header"><span className="panel-title">Collateral</span></div>
          <div className="panel-body">
            <ul style={{ listStyle: 'none', display: 'grid', gap: '0.45rem' }}>
              {fakeCall.collateral.map((c) => (
                <li key={c} style={{ fontSize: '0.78rem', color: 'var(--accent)' }}>↗ {c}</li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-header"><span className="panel-title">Transcript</span></div>
        <div className="panel-body">
          <pre style={{ maxHeight: '320px' }}>{fakeCall.transcript}</pre>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add ui/app/calls/
git commit -m "feat: clean call detail page with coaching artifact, risks, transcript"
```

---

## Task 18: Read ChatOrchestrator and wire up token pass-through

**Files:**
- Modify: `api/app/services/chat_orchestrator.py`

**Step 1: Read the file**

```bash
cat api/app/services/chat_orchestrator.py
```

**Step 2: Add `openai_token` parameter to `__init__` and pass it to LLMService**

Find where `LLMService()` is instantiated (no args today). Change it to:

```python
self.llm = LLMService(api_key=openai_token)
```

And update `__init__` signature to accept:

```python
def __init__(self, db: Session, openai_token: str | None = None) -> None:
```

**Step 3: Commit**

```bash
git add api/app/services/chat_orchestrator.py
git commit -m "feat: ChatOrchestrator accepts openai_token and passes to LLMService"
```

---

## Task 19: End-to-end smoke test

**Step 1: Start the backend**

```bash
cd api && uvicorn app.main:app --reload --port 8000
```

Expected: FastAPI starts on port 8000, no errors.

**Step 2: Start the frontend**

```bash
cd ui && npm run dev
```

Expected: Two lines — `Next.js ready on http://localhost:3000` and `OAuth callback receiver ready on http://localhost:1455`.

**Step 3: Test login flow**

1. Open `http://localhost:3000`
2. Should redirect to `/login`
3. Click "Login with ChatGPT"
4. Should redirect to `https://auth.openai.com/oauth/authorize?...`
5. Complete ChatGPT login
6. Should redirect through `localhost:1455/auth/callback` → `localhost:3000/api/auth/exchange` → `/rep`
7. Verify persona nav shows all 4 tabs

**Step 4: Test Ask Oracle**

1. On the Rep page, submit a question in Ask Oracle
2. Verify it hits `/api/oracle` (Next.js proxy)
3. Check the backend receives `X-OpenAI-Token` header
4. Verify a response comes back (or a reasonable error if OpenAI rejects the demo token)

**Step 5: Test settings**

1. Navigate to `/settings`
2. Verify email, token expiry, and auth method are shown
3. Click "Sign out" — should clear cookie and redirect to `/login`

---

## Task 20: Final cleanup and README update

**Step 1: Remove old unused components from `ui/components/`**

The following components are superseded by the new persona pages:
- `FollowUpsWidget.js` — logic is now inline in Rep page
- `MarketingOutreachWidget.js` — logic is now inline in Marketing page
- `TechnicalWizardWidget.js` — logic is now inline in SE page
- `DraftRegenerator.js` — raw JSON display replaced by call detail page; keep if still needed

Check which are still imported anywhere before deleting:

```bash
grep -r "FollowUpsWidget\|MarketingOutreachWidget\|TechnicalWizardWidget\|DraftRegenerator" ui/app ui/components
```

Delete unreferenced ones.

**Step 2: Update `README.md` dev setup section**

Add the `npm run dev` note about dual-port and the ChatGPT OAuth prerequisite.

**Step 3: Final commit**

```bash
git add -A
git commit -m "chore: remove superseded components, update README dev setup"
```

---

## Summary of all new files

```
ui/server.js
ui/middleware.js
ui/lib/pkce.js
ui/lib/session.js
ui/data/fake-calls.js
ui/app/login/page.js
ui/app/(app)/layout.js
ui/app/(app)/rep/page.js
ui/app/(app)/se/page.js
ui/app/(app)/marketing/page.js
ui/app/(app)/admin/page.js
ui/app/(app)/settings/page.js
ui/app/api/auth/start/route.js
ui/app/api/auth/exchange/route.js
ui/app/api/auth/logout/route.js
ui/app/api/auth/me/route.js
ui/app/api/oracle/route.js
ui/components/Sidebar.js
```

## Modified files

```
ui/package.json          (dev script)
ui/app/layout.js         (minimal)
ui/app/page.js           (redirect)
ui/app/globals.css       (full rewrite)
ui/app/calls/[id]/page.js (clean detail view)
ui/lib/api.js            (proxy helper)
ui/components/AskOracleWidget.js (restyled)
api/app/services/llm.py  (per-request api_key)
api/app/services/chat_orchestrator.py (token pass-through)
api/app/api/routes/chat.py (read X-OpenAI-Token header)
```

---

## Extension: Google Docs + Feishu (Lark) Knowledge Base Sources

> These tasks implement the KB source integration described in the PingCAP internal doc
> "Use OpenCode to access both Lark and Google documents simultaneously."
> Each task follows the same ingest pattern as DriveIngestor.

---

## Task 21: Add `FEISHU` to SourceType + `KBConfig` DB model

**Files:**
- Modify: `api/app/models/entities.py`
- Create: Alembic migration (auto-generated)

**Step 1: Add `FEISHU` to the `SourceType` enum in `api/app/models/entities.py`**

Find the SourceType enum:
```python
class SourceType(str, enum.Enum):
    GOOGLE_DRIVE = "google_drive"
    CHORUS = "chorus"
```

Add the new value:
```python
class SourceType(str, enum.Enum):
    GOOGLE_DRIVE = "google_drive"
    CHORUS = "chorus"
    FEISHU = "feishu"
```

**Step 2: Add `KBConfig` model at the bottom of `api/app/models/entities.py`**

```python
class KBConfig(Base):
    """Single-row config table for KB source settings. Use get_kb_config() to read."""
    __tablename__ = "kb_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    google_drive_enabled: Mapped[bool] = mapped_column(default=True)
    google_drive_folder_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    feishu_enabled: Mapped[bool] = mapped_column(default=False)
    feishu_folder_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    feishu_app_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    feishu_app_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    chorus_enabled: Mapped[bool] = mapped_column(default=True)
    retrieval_top_k: Mapped[int] = mapped_column(Integer, default=8)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

**Step 3: Export from `api/app/models/__init__.py`**

Add `KBConfig` to the imports and `__all__` list.

**Step 4: Generate and apply migration**

```bash
cd api && alembic revision --autogenerate -m "add feishu source type and kb_config table"
alembic upgrade head
```

Expected: New migration file created, applied without errors.

**Step 5: Commit**

```bash
git add api/app/models/ api/alembic/versions/
git commit -m "feat: add Feishu SourceType and KBConfig model"
```

---

## Task 22: KB Config API endpoint (backend)

**Files:**
- Modify: `api/app/api/routes/admin.py`
- Create: `api/app/schemas/kb_config.py`

**Step 1: Create `api/app/schemas/kb_config.py`**

```python
from __future__ import annotations
from pydantic import BaseModel, Field

class KBConfigUpdate(BaseModel):
    google_drive_enabled: bool = True
    google_drive_folder_id: str | None = None
    feishu_enabled: bool = False
    feishu_folder_token: str | None = None
    feishu_app_id: str | None = None
    feishu_app_secret: str | None = None
    chorus_enabled: bool = True
    retrieval_top_k: int = Field(default=8, ge=1, le=50)
```

**Step 2: Add helpers and routes to `api/app/api/routes/admin.py`**

Add these imports at the top:
```python
from app.models import KBConfig
from app.schemas.kb_config import KBConfigUpdate
```

Add a helper function:
```python
def _get_or_create_kb_config(db: Session) -> KBConfig:
    config = db.execute(select(KBConfig).where(KBConfig.id == 1)).scalar_one_or_none()
    if not config:
        config = KBConfig(id=1)
        db.add(config)
        db.flush()
    return config
```

Add two new routes:
```python
@router.get("/kb-config")
def get_kb_config(db: Session = Depends(db_session)) -> dict:
    config = _get_or_create_kb_config(db)
    db.commit()
    return {
        "google_drive_enabled": config.google_drive_enabled,
        "google_drive_folder_id": config.google_drive_folder_id,
        "feishu_enabled": config.feishu_enabled,
        "feishu_folder_token": config.feishu_folder_token,
        "feishu_app_id": config.feishu_app_id,
        # Never return the secret — just whether it's set
        "feishu_app_secret_set": bool(config.feishu_app_secret),
        "chorus_enabled": config.chorus_enabled,
        "retrieval_top_k": config.retrieval_top_k,
        "updated_at": config.updated_at,
    }


@router.put("/kb-config")
def update_kb_config(body: KBConfigUpdate, db: Session = Depends(db_session)) -> dict:
    config = _get_or_create_kb_config(db)
    config.google_drive_enabled = body.google_drive_enabled
    config.google_drive_folder_id = body.google_drive_folder_id
    config.feishu_enabled = body.feishu_enabled
    config.feishu_folder_token = body.feishu_folder_token
    config.feishu_app_id = body.feishu_app_id
    if body.feishu_app_secret:
        config.feishu_app_secret = body.feishu_app_secret
    config.chorus_enabled = body.chorus_enabled
    config.retrieval_top_k = body.retrieval_top_k
    db.commit()
    return {"ok": True, "retrieval_top_k": config.retrieval_top_k}
```

**Step 3: Add Feishu sync route**

```python
@router.post("/sync/feishu")
def sync_feishu(db: Session = Depends(db_session)) -> dict:
    from app.ingest.feishu_ingestor import FeishuIngestor
    config = _get_or_create_kb_config(db)
    if not config.feishu_enabled:
        return {"skipped": True, "reason": "Feishu source not enabled"}
    if not config.feishu_app_id or not config.feishu_app_secret:
        return {"skipped": True, "reason": "Feishu credentials not configured"}
    ingestor = FeishuIngestor(
        db,
        app_id=config.feishu_app_id,
        app_secret=config.feishu_app_secret,
        folder_token=config.feishu_folder_token,
    )
    result = ingestor.sync()
    write_audit_log(db, actor="system", action="sync_feishu",
                    input_payload={}, retrieval_payload={}, output_payload=result, status=AuditStatus.OK)
    return result
```

**Step 4: Commit**

```bash
git add api/app/api/routes/admin.py api/app/schemas/kb_config.py
git commit -m "feat: /admin/kb-config GET+PUT and /admin/sync/feishu endpoints"
```

---

## Task 23: Feishu connector + ingestor

**Files:**
- Create: `api/app/ingest/feishu_connector.py`
- Create: `api/app/ingest/feishu_ingestor.py`

**Step 1: Create `api/app/ingest/feishu_connector.py`**

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

import requests


LARK_BASE = "https://open.feishu.cn/open-apis"


@dataclass
class FeishuFile:
    file_token: str
    title: str
    url: str
    owner: str
    modified_time: datetime
    content: str
    mime: str = "application/vnd.feishu.doc"


class FeishuConnector:
    def __init__(self, app_id: str, app_secret: str, folder_token: str | None = None) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.folder_token = folder_token
        self._tenant_token: str | None = None

    def _get_tenant_token(self) -> str:
        if self._tenant_token:
            return self._tenant_token
        res = requests.post(
            f"{LARK_BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=10,
        )
        res.raise_for_status()
        self._tenant_token = res.json()["tenant_access_token"]
        return self._tenant_token

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_tenant_token()}"}

    def _list_files_in_folder(self, folder_token: str) -> list[dict]:
        params = {"folder_token": folder_token, "page_size": 50}
        res = requests.get(f"{LARK_BASE}/drive/v1/files", headers=self._auth_headers(), params=params, timeout=10)
        res.raise_for_status()
        return res.json().get("data", {}).get("files", [])

    def _get_doc_content(self, doc_token: str) -> str:
        res = requests.get(
            f"{LARK_BASE}/docx/v1/documents/{doc_token}/raw_content",
            headers=self._auth_headers(),
            timeout=15,
        )
        if not res.ok:
            return ""
        return res.json().get("data", {}).get("content", "")

    def list_files(self) -> list[FeishuFile]:
        results: list[FeishuFile] = []
        folder = self.folder_token or "root"
        raw_files = self._list_files_in_folder(folder)

        for f in raw_files:
            file_type = f.get("type", "")
            if file_type not in ("doc", "docx", "sheet"):
                continue  # only process document types

            token = f.get("token", "")
            title = f.get("name", "Untitled")
            url = f.get("url", f"https://www.feishu.cn/docs/{token}")
            owner = f.get("owner_id", "")
            modified_ms = f.get("modified_time", 0)
            modified_dt = datetime.fromtimestamp(int(modified_ms)) if modified_ms else datetime.now()

            content = self._get_doc_content(token)

            results.append(FeishuFile(
                file_token=token,
                title=title,
                url=url,
                owner=owner,
                modified_time=modified_dt,
                content=content,
            ))

        return results
```

**Step 2: Create `api/app/ingest/feishu_ingestor.py`**

```python
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ingest.feishu_connector import FeishuConnector, FeishuFile
from app.models import KBDocument, KBChunk, SourceType
from app.services.embedding import EmbeddingService
from app.utils.chunking import chunk_markdown_heading_aware
from app.utils.hashing import sha256_text


class FeishuIngestor:
    def __init__(self, db: Session, app_id: str, app_secret: str, folder_token: str | None = None) -> None:
        self.db = db
        self.connector = FeishuConnector(app_id=app_id, app_secret=app_secret, folder_token=folder_token)
        self.embedder = EmbeddingService()

    def _upsert_document(self, file: FeishuFile) -> tuple[KBDocument, bool]:
        existing = self.db.execute(
            select(KBDocument).where(
                KBDocument.source_type == SourceType.FEISHU,
                KBDocument.source_id == file.file_token,
            )
        ).scalar_one_or_none()

        if existing:
            if existing.modified_time and existing.modified_time >= file.modified_time:
                return existing, False
            existing.title = file.title
            existing.url = file.url
            existing.modified_time = file.modified_time
            existing.owner = file.owner
            doc = existing
        else:
            doc = KBDocument(
                source_type=SourceType.FEISHU,
                source_id=file.file_token,
                title=file.title,
                url=file.url,
                modified_time=file.modified_time,
                owner=file.owner,
                tags={"source_type": "feishu"},
            )
            self.db.add(doc)

        self.db.flush()
        return doc, True

    def sync(self) -> dict:
        files = self.connector.list_files()
        indexed, skipped = 0, 0

        for file in files:
            doc, changed = self._upsert_document(file)
            if not changed:
                skipped += 1
                continue

            self.db.execute(delete(KBChunk).where(KBChunk.document_id == doc.id))
            chunks = chunk_markdown_heading_aware(file.content or "")
            embeddings = self.embedder.batch_embed([c.text for c in chunks]) if chunks else []

            for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                self.db.add(KBChunk(
                    document_id=doc.id,
                    chunk_index=idx,
                    text=chunk.text,
                    token_count=chunk.token_count,
                    embedding=emb,
                    metadata_json=chunk.metadata,
                    content_hash=sha256_text(chunk.text),
                ))
            indexed += 1

        self.db.commit()
        return {"files_seen": len(files), "indexed": indexed, "skipped": skipped}
```

**Step 3: Commit**

```bash
git add api/app/ingest/feishu_connector.py api/app/ingest/feishu_ingestor.py
git commit -m "feat: Feishu connector and ingestor — list docs via Lark API, chunk and embed"
```

---

## Task 24: Wire `retrieval_top_k` from KBConfig into retrieval

**Files:**
- Read first: `api/app/retrieval/` directory — find where top_k is used
- Modify: the retrieval service or chat orchestrator

**Step 1: Inspect retrieval code**

```bash
ls api/app/retrieval/
cat api/app/retrieval/*.py
```

**Step 2: Modify the retrieval call to read top_k from KBConfig**

Find where `retrieval_top_k` from settings is used. Update `ChatOrchestrator.run()` (or wherever the retrieval is triggered) to:

```python
from app.models import KBConfig
from sqlalchemy import select

# Inside run() or wherever top_k is determined:
config = db.execute(select(KBConfig).where(KBConfig.id == 1)).scalar_one_or_none()
effective_top_k = config.retrieval_top_k if config else top_k
```

Also filter which source types are queried based on `config.google_drive_enabled`, `config.feishu_enabled`, `config.chorus_enabled`. Pass the enabled source types as a filter to the retrieval query.

**Step 3: Commit**

```bash
git add api/app/services/chat_orchestrator.py api/app/retrieval/
git commit -m "feat: retrieval respects KBConfig top_k and source enable/disable flags"
```

---

## Task 25: Admin panel KB configuration UI

**Files:**
- Modify: `ui/app/(app)/admin/page.js`
- Create: `ui/components/KBConfigPanel.js`

**Step 1: Create `ui/components/KBConfigPanel.js`**

```js
'use client';

import { useEffect, useState } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

const DEPTH_OPTIONS = [
  { value: 4,  label: '4  — Fast, narrow (top 4 chunks)' },
  { value: 8,  label: '8  — Balanced (default)' },
  { value: 16, label: '16 — Deep, broader context' },
  { value: 32, label: '32 — Maximum (slow, comprehensive)' },
];

export default function KBConfigPanel() {
  const [config, setConfig] = useState(null);
  const [saving, setSaving] = useState(false);
  const [syncing, setSyncing] = useState('');
  const [message, setMessage] = useState('');

  useEffect(() => {
    fetch(`${API_BASE}/admin/kb-config`)
      .then((r) => r.json())
      .then(setConfig)
      .catch(() => setMessage('Could not load KB config — is the API running?'));
  }, []);

  const save = async () => {
    setSaving(true);
    setMessage('');
    try {
      const res = await fetch(`${API_BASE}/admin/kb-config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          google_drive_enabled: config.google_drive_enabled,
          google_drive_folder_id: config.google_drive_folder_id || null,
          feishu_enabled: config.feishu_enabled,
          feishu_folder_token: config.feishu_folder_token || null,
          feishu_app_id: config.feishu_app_id || null,
          feishu_app_secret: config.feishu_app_secret || null,
          chorus_enabled: config.chorus_enabled,
          retrieval_top_k: config.retrieval_top_k,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setMessage('Saved.');
    } catch (err) {
      setMessage(`Error: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const sync = async (source) => {
    setSyncing(source);
    setMessage('');
    try {
      const res = await fetch(`${API_BASE}/admin/sync/${source}`, { method: 'POST' });
      const data = await res.json();
      setMessage(`Sync ${source}: ${JSON.stringify(data)}`);
    } catch (err) {
      setMessage(`Sync error: ${err.message}`);
    } finally {
      setSyncing('');
    }
  };

  const set = (key, value) => setConfig((prev) => ({ ...prev, [key]: value }));

  if (!config) return <div style={{ color: 'var(--text-3)', fontSize: '0.8rem', padding: '0.85rem' }}>Loading KB config...</div>;

  return (
    <div style={{ display: 'grid', gap: '1.25rem' }}>

      {/* Retrieval depth */}
      <div className="panel">
        <div className="panel-header">
          <span className="panel-title">Retrieval Depth</span>
          <span className="tag tag-orange">top_k = {config.retrieval_top_k}</span>
        </div>
        <div className="panel-body" style={{ display: 'grid', gap: '0.5rem' }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-3)', marginBottom: '0.25rem' }}>
            How many document chunks are retrieved per query. Higher = more context, slower response.
          </div>
          {DEPTH_OPTIONS.map((opt) => (
            <label key={opt.value} style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', cursor: 'pointer', fontSize: '0.82rem', color: config.retrieval_top_k === opt.value ? 'var(--accent)' : 'var(--text-2)' }}>
              <input
                type="radio"
                name="top_k"
                value={opt.value}
                checked={config.retrieval_top_k === opt.value}
                onChange={() => set('retrieval_top_k', opt.value)}
                style={{ accentColor: 'var(--accent)' }}
              />
              {opt.label}
            </label>
          ))}
        </div>
      </div>

      {/* Google Drive */}
      <div className="panel">
        <div className="panel-header">
          <span className="panel-title">Google Drive</span>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.78rem', color: 'var(--text-2)' }}>
            <input type="checkbox" checked={config.google_drive_enabled} onChange={(e) => set('google_drive_enabled', e.target.checked)} style={{ accentColor: 'var(--accent)' }} />
            Enabled
          </label>
        </div>
        <div className="panel-body" style={{ display: 'grid', gap: '0.65rem' }}>
          <div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-3)', marginBottom: '0.3rem' }}>Folder ID (leave blank for root)</div>
            <input
              className="input"
              placeholder="e.g. 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"
              value={config.google_drive_folder_id || ''}
              onChange={(e) => set('google_drive_folder_id', e.target.value)}
            />
          </div>
          <button className="btn" disabled={syncing === 'drive'} onClick={() => sync('drive')}>
            {syncing === 'drive' ? 'Syncing...' : 'Sync Google Drive now'}
          </button>
        </div>
      </div>

      {/* Feishu / Lark */}
      <div className="panel">
        <div className="panel-header">
          <span className="panel-title">Feishu (Lark)</span>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.78rem', color: 'var(--text-2)' }}>
            <input type="checkbox" checked={config.feishu_enabled} onChange={(e) => set('feishu_enabled', e.target.checked)} style={{ accentColor: 'var(--accent)' }} />
            Enabled
          </label>
        </div>
        <div className="panel-body" style={{ display: 'grid', gap: '0.65rem' }}>
          <div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-3)', marginBottom: '0.3rem' }}>Lark App ID</div>
            <input className="input" placeholder="cli_a..." value={config.feishu_app_id || ''} onChange={(e) => set('feishu_app_id', e.target.value)} />
          </div>
          <div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-3)', marginBottom: '0.3rem' }}>
              Lark App Secret {config.feishu_app_secret_set ? <span style={{ color: 'var(--success)' }}>✓ set</span> : '(not set)'}
            </div>
            <input className="input" type="password" placeholder="Leave blank to keep existing" value={config.feishu_app_secret || ''} onChange={(e) => set('feishu_app_secret', e.target.value)} />
          </div>
          <div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-3)', marginBottom: '0.3rem' }}>Folder Token (leave blank for root)</div>
            <input className="input" placeholder="e.g. fldbc..." value={config.feishu_folder_token || ''} onChange={(e) => set('feishu_folder_token', e.target.value)} />
          </div>
          <button className="btn" disabled={syncing === 'feishu' || !config.feishu_enabled} onClick={() => sync('feishu')}>
            {syncing === 'feishu' ? 'Syncing...' : 'Sync Feishu now'}
          </button>
          <div style={{ fontSize: '0.72rem', color: 'var(--text-3)' }}>
            Requires a Lark app with <code>drive:drive:readonly</code> and <code>docx:document:readonly</code> scopes.
            Create one at <span style={{ color: 'var(--accent)' }}>open.feishu.cn/app</span>.
          </div>
        </div>
      </div>

      {/* Chorus */}
      <div className="panel">
        <div className="panel-header">
          <span className="panel-title">Chorus (Call Transcripts)</span>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.78rem', color: 'var(--text-2)' }}>
            <input type="checkbox" checked={config.chorus_enabled} onChange={(e) => set('chorus_enabled', e.target.checked)} style={{ accentColor: 'var(--accent)' }} />
            Enabled
          </label>
        </div>
        <div className="panel-body">
          <button className="btn" disabled={syncing === 'chorus'} onClick={() => sync('chorus')}>
            {syncing === 'chorus' ? 'Syncing...' : 'Sync Chorus now'}
          </button>
        </div>
      </div>

      {/* Save + status */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <button className="btn btn-primary" onClick={save} disabled={saving}>
          {saving ? 'Saving...' : 'Save KB Configuration'}
        </button>
        {message && <span style={{ fontSize: '0.78rem', color: message.startsWith('Error') ? 'var(--danger)' : 'var(--success)' }}>{message}</span>}
      </div>
    </div>
  );
}
```

**Step 2: Add KB config panel to Admin page**

In `ui/app/(app)/admin/page.js`, import and add the panel:

```js
import KBConfigPanel from '../../../components/KBConfigPanel';
```

Then inside the `<div className="content">` after the existing panels, add:

```js
{/* KB Source Configuration */}
<div style={{ marginTop: '0.5rem' }}>
  <div style={{ fontSize: '0.72rem', color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.75rem' }}>
    Knowledge Base Sources
  </div>
  <KBConfigPanel />
</div>
```

**Step 3: Commit**

```bash
git add ui/components/KBConfigPanel.js ui/app/\(app\)/admin/page.js
git commit -m "feat: Admin panel KB source configuration — Google Drive, Feishu, Chorus toggles + retrieval depth"
```

---

## Task 26: End-to-end KB config smoke test

**Step 1: Start both servers**

```bash
# Terminal 1
cd api && uvicorn app.main:app --reload --port 8000

# Terminal 2
cd ui && npm run dev
```

**Step 2: Verify KB config API**

```bash
curl http://localhost:8000/admin/kb-config
```

Expected: JSON with default values (`google_drive_enabled: true`, `feishu_enabled: false`, `retrieval_top_k: 8`).

**Step 3: Test save from Admin UI**

1. Navigate to `http://localhost:3000/admin`
2. Scroll to "Knowledge Base Sources"
3. Change retrieval depth to `16`
4. Enable Feishu, enter a test App ID
5. Click "Save KB Configuration"
6. Re-run the curl above — verify `retrieval_top_k: 16` is returned

**Step 4: Verify retrieval respects top_k**

Ask Oracle a question, check backend logs confirm the new top_k value is being used.

**Step 5: Commit**

```bash
git add -A
git commit -m "chore: KB config extension complete — Feishu + Google Drive configurable from Admin panel"
```

---

## Summary of Extension Files

**New backend files:**
```
api/app/ingest/feishu_connector.py     Lark API client — token auth, list files, get doc content
api/app/ingest/feishu_ingestor.py      Chunk + embed Feishu docs into KB (same pattern as DriveIngestor)
api/app/schemas/kb_config.py           Pydantic schema for KB config update
api/alembic/versions/<hash>_kb.py      Migration: add feishu SourceType + kb_config table
```

**Modified backend files:**
```
api/app/models/entities.py             Add SourceType.FEISHU + KBConfig model
api/app/models/__init__.py             Export KBConfig
api/app/api/routes/admin.py            Add /kb-config GET+PUT and /sync/feishu
api/app/services/chat_orchestrator.py  Read top_k + source filters from KBConfig
```

**New frontend files:**
```
ui/components/KBConfigPanel.js         Interactive KB source config panel with depth radio + source toggles
```

**Modified frontend files:**
```
ui/app/(app)/admin/page.js             Add KBConfigPanel section
```
