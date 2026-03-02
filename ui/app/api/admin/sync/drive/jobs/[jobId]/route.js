import { getSession } from '@/lib/session';

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000';

export async function GET(_request, { params }) {
  const session = await getSession();
  const jobId = params?.jobId;
  const res = await fetch(`${API_BASE}/admin/sync/drive/jobs/${encodeURIComponent(jobId)}`, {
    headers: session
      ? {
          'X-OpenAI-Token': session.access_token,
          'X-User-Email': session.email || '',
        }
      : {},
    cache: 'no-store',
  });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
