import { getSession } from '@/lib/session';

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000';

export async function POST(request) {
  const session = await getSession();
  const body = await request.json().catch(() => ({}));
  const since = body?.since ? `?since=${encodeURIComponent(body.since)}` : '';
  const res = await fetch(`${API_BASE}/admin/sync/drive/start${since}`, {
    method: 'POST',
    headers: session
      ? {
          'X-OpenAI-Token': session.access_token,
          'X-User-Email': session.email || '',
        }
      : {},
  });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
