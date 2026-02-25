import { NextResponse } from 'next/server';

const PROTECTED = ['/rep', '/se', '/marketing', '/admin', '/settings'];

export function middleware(request) {
  const { pathname } = request.nextUrl;

  const isProtected = PROTECTED.some((p) => pathname.startsWith(p));
  if (!isProtected) return NextResponse.next();

  const session = request.cookies.get('oracle_session')?.value;
  if (!session) {
    return NextResponse.redirect(new URL('/login', request.url));
  }

  try {
    const parsed = JSON.parse(session);
    if (!parsed.access_token || Date.now() > parsed.expires_at) {
      return NextResponse.redirect(new URL('/login?error=expired', request.url));
    }
  } catch {
    return NextResponse.redirect(new URL('/login', request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/rep/:path*', '/se/:path*', '/marketing/:path*', '/admin/:path*', '/settings/:path*'],
};
