// Phase 21 — shared helpers for the portal's own session cookies. The actual
// JWTs are issued/verified by FastAPI (fastapi/auth.py); the portal only
// stores them as HttpOnly cookies and forwards them — it never decodes or
// trusts them itself (the BFF route still relies on FastAPI's 401 to know a
// token is bad).

export const ACCESS_COOKIE = 'diep_at';
export const REFRESH_COOKIE = 'diep_rt';
export const ROLE_COOKIE = 'diep_role';
export const USER_COOKIE = 'diep_user';

export const API_BASE = process.env.DIEP_API_BASE || 'http://diep-fastapi:8000';

export function sessionCookieOptions(maxAgeSeconds: number, httpOnly = true) {
  return {
    httpOnly,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax' as const,
    path: '/',
    maxAge: maxAgeSeconds,
  };
}

export const ALL_SESSION_COOKIES = [ACCESS_COOKIE, REFRESH_COOKIE, ROLE_COOKIE, USER_COOKIE];
