// Phase 9J — portal BFF with server-side auth injection.
//
// The browser calls the portal's own origin (/api/diep/*); this server-side route
// handler forwards to FastAPI over diep-net AND attaches the portal's API token as
// a Bearer header. The token lives only in server env (DIEP_PORTAL_TOKEN) and is
// never exposed to the browser — replacing the old transparent next.config rewrite,
// which could not add the now-required Authorization header.
//
// The portal token is admin-scoped (the console performs both operator DERMS actions
// and admin registration/onboarding). Production should replace this shared token
// with per-operator SSO/JWT via the /auth/token login flow.

import { NextRequest, NextResponse } from 'next/server';

const BASE = process.env.DIEP_API_BASE || 'http://diep-fastapi:8000';
const TOKEN = process.env.DIEP_PORTAL_TOKEN || 'diep-admin-dev-key-CHANGE-ME';

async function forward(req: NextRequest, path: string[]): Promise<NextResponse> {
  const search = req.nextUrl.search || '';
  const url = `${BASE}/${path.join('/')}${search}`;

  const headers: Record<string, string> = {
    Authorization: `Bearer ${TOKEN}`,
    Accept: 'application/json',
  };
  const init: RequestInit = { method: req.method, headers };

  if (req.method !== 'GET' && req.method !== 'HEAD') {
    const body = await req.text();
    if (body) {
      init.body = body;
      headers['Content-Type'] = req.headers.get('content-type') || 'application/json';
    }
  }

  try {
    const res = await fetch(url, init);
    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: { 'Content-Type': res.headers.get('content-type') || 'application/json' },
    });
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
