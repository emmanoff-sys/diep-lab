import { NextRequest, NextResponse } from 'next/server';
import {
  API_BASE, ACCESS_COOKIE, REFRESH_COOKIE, ROLE_COOKIE, USER_COOKIE, sessionCookieOptions,
} from '@/lib/serverAuth';

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => null);
  if (!body?.username || !body?.password) {
    return NextResponse.json({ detail: 'username and password are required' }, { status: 400 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${API_BASE}/auth/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: body.username, password: body.password }),
    });
  } catch (err) {
    return NextResponse.json({ detail: `auth backend unreachable: ${err}` }, { status: 502 });
  }

  const data = await upstream.json().catch(() => ({}));
  if (!upstream.ok) {
    return NextResponse.json(data, { status: upstream.status });
  }

  const res = NextResponse.json({ username: body.username, role: data.role, tenant: data.tenant });
  res.cookies.set(ACCESS_COOKIE, data.access_token, sessionCookieOptions(data.expires_in || 3600));
  res.cookies.set(REFRESH_COOKIE, data.refresh_token, sessionCookieOptions(30 * 24 * 3600));
  res.cookies.set(ROLE_COOKIE, data.role, sessionCookieOptions(30 * 24 * 3600, false));
  res.cookies.set(USER_COOKIE, body.username, sessionCookieOptions(30 * 24 * 3600, false));
  return res;
}
