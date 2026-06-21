// Phase 9J — portal BFF, rewritten in Phase 21 for per-user auth.
//
// The browser calls the portal's own origin (/api/diep/*); this server-side route
// handler forwards to FastAPI over diep-net, attaching the *caller's own* session
// JWT (from the HttpOnly diep_at cookie set at /api/auth/login) as the Bearer
// header — never a shared, admin-scoped credential. This means FastAPI's real
// RBAC (fastapi/auth.py's require_role()) now actually applies per user: a
// viewer's token gets a 403 from admin-only endpoints exactly as it would for
// any other API client.
//
// On a 401 (expired access token), this proxy transparently exchanges the
// refresh-token cookie for a new access token once and retries, so a normal
// browsing session doesn't get interrupted every hour — only once both
// access and refresh are gone does the caller see a real 401, at which point
// the client-side SWR error handler (see components/Providers.tsx) sends the
// browser back to /login.

import { NextRequest, NextResponse } from 'next/server';
import { API_BASE, ACCESS_COOKIE, REFRESH_COOKIE, sessionCookieOptions } from '@/lib/serverAuth';

async function refreshAccessToken(refreshToken: string): Promise<{ access_token: string; expires_in: number } | null> {
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

async function forward(req: NextRequest, path: string[]): Promise<NextResponse> {
  const search = req.nextUrl.search || '';
  const url = `${API_BASE}/${path.join('/')}${search}`;
  const accessToken = req.cookies.get(ACCESS_COOKIE)?.value;

  let bodyText: string | undefined;
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    bodyText = await req.text();
  }

  function doFetch(token?: string): Promise<Response> {
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (token) headers.Authorization = `Bearer ${token}`;
    const init: RequestInit = { method: req.method, headers };
    if (bodyText) {
      init.body = bodyText;
      headers['Content-Type'] = req.headers.get('content-type') || 'application/json';
    }
    return fetch(url, init);
  }

  try {
    let res = await doFetch(accessToken);
    let refreshedAccessToken: string | null = null;

    if (res.status === 401 && accessToken) {
      const refreshToken = req.cookies.get(REFRESH_COOKIE)?.value;
      if (refreshToken) {
        const refreshed = await refreshAccessToken(refreshToken);
        if (refreshed) {
          refreshedAccessToken = refreshed.access_token;
          res = await doFetch(refreshedAccessToken);
        }
      }
    }

    const text = await res.text();
    const out = new NextResponse(text, {
      status: res.status,
      headers: { 'Content-Type': res.headers.get('content-type') || 'application/json' },
    });
    if (refreshedAccessToken) {
      out.cookies.set(ACCESS_COOKIE, refreshedAccessToken, sessionCookieOptions(3600));
    }
    return out;
  } catch (err) {
    return NextResponse.json({ detail: `proxy error: ${err}` }, { status: 502 });
  }
}

type Ctx = { params: { path: string[] } };

export async function GET(req: NextRequest, ctx: Ctx) {
  return forward(req, ctx.params.path);
}
export async function POST(req: NextRequest, ctx: Ctx) {
  return forward(req, ctx.params.path);
}
export async function PUT(req: NextRequest, ctx: Ctx) {
  return forward(req, ctx.params.path);
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  return forward(req, ctx.params.path);
}
export async function PATCH(req: NextRequest, ctx: Ctx) {
  return forward(req, ctx.params.path);
}
