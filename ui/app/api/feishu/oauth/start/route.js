import { getSession } from '@/lib/session';

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000';

export async function GET(request) {
  const session = await getSession();
  if (!session?.email) {
    return Response.json({ error: 'unauthenticated' }, { status: 401 });
  }

  const callbackUrl = new URL('/api/feishu/oauth/callback', request.url).toString();
  const qs = new URLSearchParams({ redirect_uri: callbackUrl });
  const res = await fetch(`${API_BASE}/admin/feishu/oauth/start?${qs}`, {
    headers: {
      'X-User-Email': session.email,
      ...(session.access_token ? { 'X-OpenAI-Token': session.access_token } : {}),
    },
    cache: 'no-store',
  });
  const payload = await res.json();
  return Response.json(payload, { status: res.status });
}
