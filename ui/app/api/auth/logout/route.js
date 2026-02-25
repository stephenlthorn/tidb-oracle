import { NextResponse } from 'next/server';

export async function POST() {
  const res = NextResponse.redirect(new URL('/login', 'http://localhost:3000'));
  res.cookies.set('oracle_session', '', { httpOnly: true, path: '/', maxAge: 0 });
  return res;
}
