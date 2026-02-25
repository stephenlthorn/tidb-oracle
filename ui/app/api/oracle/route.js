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

  const text = await res.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    data = { error: `API error: ${text.slice(0, 200)}` };
  }
  return NextResponse.json(data, { status: res.status });
}
