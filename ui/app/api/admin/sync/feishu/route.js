import { getSession } from '@/lib/session';

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000';

export async function POST() {
  const session = await getSession();
  const res = await fetch(`${API_BASE}/admin/sync/feishu`, {
    method: 'POST',
    headers: session ? { 'X-OpenAI-Token': session.access_token } : {},
  });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
