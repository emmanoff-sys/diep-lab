'use client';

import { useState } from 'react';

export default function ForgotPasswordPage() {
  const [username, setUsername] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [resetLink, setResetLink] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    setResetLink(null);
    try {
      const res = await fetch('/api/auth/password-reset/request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
      setMsg('If that account exists, a reset link has been issued.');
      if (data.reset_token) {
        setResetLink(`/reset-password?token=${encodeURIComponent(data.reset_token)}`);
      }
    } catch (e: any) {
      setErr(e.message);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0b0e12]">
      <form onSubmit={submit} className="w-full max-w-sm bg-[#11161c] border border-[#232a33] rounded-lg p-6">
        <div className="text-lg font-semibold text-white mb-1">DIEP</div>
        <div className="text-xs text-[#8b95a1] mb-6">Request a password reset</div>
        <label className="block text-xs text-[#8b95a1] mb-1">Username</label>
        <input
          autoFocus
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="w-full bg-[#0f1419] border border-[#232a33] rounded px-2 py-1.5 text-sm mb-4 text-white"
        />
        <button
          type="submit"
          disabled={!username}
          className="w-full bg-[#2563eb] hover:bg-[#1d4ed8] disabled:opacity-50 text-white text-sm rounded px-4 py-2"
        >
          Request reset
        </button>
        {msg && <div className="text-[#4ade80] text-sm mt-3">{msg}</div>}
        {err && <div className="text-[#f87171] text-sm mt-3">{err}</div>}
        {resetLink && (
          <div className="text-xs text-[#8b95a1] mt-3">
            Lab/demo mode (no email integration yet) — reset link:{' '}
            <a href={resetLink} className="text-[#5aa9e6] hover:underline">{resetLink}</a>
          </div>
        )}
        <div className="mt-4 text-xs text-center">
          <a href="/login" className="text-[#5aa9e6] hover:underline">Back to sign in</a>
        </div>
      </form>
    </div>
  );
}
