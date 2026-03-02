import { getSession } from '@/lib/session';

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000';

export async function GET(request) {
  const session = await getSession();
  const query = new URL(request.url);
  const q = (query.searchParams.get('q') || '').trim();
  const sourceType = (query.searchParams.get('source_type') || '').trim();
  const limit = (query.searchParams.get('limit') || '60').trim();

  if (!q || q.length < 2) {
    return Response.json({ query: q, results: [] }, { status: 200 });
  }

  const upstream = new URL(`${API_BASE}/kb/fulltext`);
  upstream.searchParams.set('q', q);
  upstream.searchParams.set('limit', limit);
  if (sourceType) {
    upstream.searchParams.set('source_type', sourceType);
  }

  const headers = {};
  if (session?.email) {
    headers['X-User-Email'] = session.email;
  }

  const res = await fetch(upstream.toString(), {
    headers,
    cache: 'no-store',
  });
  const payload = await res.json();
  return Response.json(payload, { status: res.status });
}
