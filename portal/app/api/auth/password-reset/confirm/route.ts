import { NextRequest, NextResponse } from 'next/server';
import { API_BASE } from '@/lib/serverAuth';

export async function POST(req: NextRequest) {
  const body = await req.text();
  try {
    const upstream = await fetch(`${API_BASE}/auth/password-reset/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
    });
    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: { 'Content-Type': upstream.headers.get('content-type') || 'application/json' },
    });
  } catch (err) {
    return NextResponse.json({ detail: `proxy error: ${err}` }, { status: 502 });
  }
}
