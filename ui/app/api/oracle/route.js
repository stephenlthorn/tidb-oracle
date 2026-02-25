import { NextResponse } from 'next/server';
import { getSession } from '../../../lib/session';

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000';

export async function POST(request) {
  const session = await getSession();

  const body = await request.json();
  const headers = {
    'Content-Type': 'application/json',
  };
  if (session?.access_token) {
    headers['X-OpenAI-Token'] = session.access_token;
  }
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ ...body, user: session?.email || body?.user || 'oracle@pingcap.com' }),
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
