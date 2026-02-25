import { NextResponse } from 'next/server';
import { getSession } from '../../../../lib/session';

export async function GET() {
  const session = await getSession();
  if (!session) return NextResponse.json({ error: 'unauthenticated' }, { status: 401 });
  return NextResponse.json({ email: session.email, name: session.name, expires_at: session.expires_at });
}
