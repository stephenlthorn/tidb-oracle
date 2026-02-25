import { NextResponse } from 'next/server';

export function middleware(request) {
  return NextResponse.next();
}

export const config = {
  matcher: ['/rep/:path*', '/se/:path*', '/marketing/:path*', '/admin/:path*', '/settings/:path*'],
};
