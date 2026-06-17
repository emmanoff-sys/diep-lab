import { NextRequest, NextResponse } from 'next/server';
import { API_BASE, ACCESS_COOKIE, ALL_SESSION_COOKIES, sessionCookieOptions } from '@/lib/serverAuth';

export async function POST(req: NextRequest) {
  const token = req.cookies.get(ACCESS_COOKIE)?.value;
  if (token) {
    try {
      await fetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch {
      // best-effort server-side revocation; cookies are cleared regardless
    }
  }

  const res = NextResponse.json({ status: 'logged_out' });
  for (const name of ALL_SESSION_COOKIES) {
    res.cookies.set(name, '', { ...sessionCookieOptions(0), maxAge: 0 });
  }
  return res;
}
