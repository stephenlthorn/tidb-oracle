import { getSession } from '@/lib/session';

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000';

export async function DELETE() {
  const session = await getSession();
  if (!session?.email) {
    return Response.json({ connected: false, error: 'unauthenticated' }, { status: 401 });
  }

  const res = await fetch(`${API_BASE}/admin/feishu/credentials`, {
    method: 'DELETE',
    headers: {
      'X-User-Email': session.email,
      ...(session.access_token ? { 'X-OpenAI-Token': session.access_token } : {}),
    },
  });
  const payload = await res.json();
  return Response.json(payload, { status: res.status });
}
