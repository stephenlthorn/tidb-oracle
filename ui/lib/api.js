function getApiBase() {
  if (typeof window === 'undefined') {
    return process.env.API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
  }
  return process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
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
