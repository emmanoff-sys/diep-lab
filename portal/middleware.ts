// Phase 21 — the authentication boundary that didn't previously exist
// (Phase 20 PORTAL-1): every route except the auth pages/APIs themselves now
// requires a non-expired access OR refresh-token cookie, redirecting to
// /login otherwise. This is a UX gate, not the security boundary — the real
// enforcement is FastAPI's require_role(), which the BFF (app/api/diep/...)
// now reaches with the caller's own token instead of a shared admin one.
import { NextRequest, NextResponse } from 'next/server';

const PUBLIC_PREFIXES = ['/login', '/forgot-password', '/reset-password', '/api/auth', '/public'];

function base64UrlDecode(input: string): string {
  const base64 = input.replace(/-/g, '+').replace(/_/g, '/');
  const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
  return atob(padded);
}

function isLiveJwt(token: string | undefined): boolean {
  if (!token) return false;
  try {
    const payload = JSON.parse(base64UrlDecode(token.split('.')[1]));
    return typeof payload.exp === 'number' && payload.exp * 1000 > Date.now();
  } catch {
    return false;
  }
}

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  if (
    PUBLIC_PREFIXES.some((p) => pathname.startsWith(p)) ||
    pathname.startsWith('/_next') ||
    pathname === '/manifest.webmanifest' ||
    pathname === '/sw.js' ||
    /\.(png|svg|ico|jpg|jpeg|webmanifest)$/.test(pathname)
  ) {
    return NextResponse.next();
  }

  const accessOk = isLiveJwt(req.cookies.get('diep_at')?.value);
  const refreshOk = isLiveJwt(req.cookies.get('diep_rt')?.value);
  if (!accessOk && !refreshOk) {
    const loginUrl = new URL('/login', req.url);
    loginUrl.searchParams.set('next', pathname);
    return NextResponse.redirect(loginUrl);
  }

  // UX-level role gate for the admin/engineer-only area; FastAPI still
  // rejects any actual write a viewer/operator might otherwise reach.
  if (pathname.startsWith('/administration')) {
    const role = req.cookies.get('diep_role')?.value;
    if (role && !['admin', 'engineer'].includes(role)) {
      return NextResponse.redirect(new URL('/?denied=administration', req.url));
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};
