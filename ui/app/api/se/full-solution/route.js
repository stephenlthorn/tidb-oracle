import { getSession } from '@/lib/session';

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000';

export async function POST(request) {
  const session = await getSession();
  const body = await request.json();

  const res = await fetch(`${API_BASE}/se/full-solution`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(session?.access_token ? { 'X-OpenAI-Token': session.access_token } : {}),
    },
    body: JSON.stringify({
      ...body,
      user: session?.email || body?.user || 'oracle@pingcap.com',
    }),
  });

  const text = await res.text();
  let payload;
  try {
    payload = JSON.parse(text);
  } catch {
    payload = { error: text.slice(0, 200) || 'Unknown API error' };
  }
  return Response.json(payload, { status: res.status });
}
