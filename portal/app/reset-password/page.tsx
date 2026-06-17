'use client';

import { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

function ResetForm() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get('token') || '';
  const [newPassword, setNewPassword] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    try {
      const res = await fetch('/api/auth/password-reset/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reset_token: token, new_password: newPassword }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Reset failed (${res.status})`);
      setMsg('Password updated. Redirecting to sign in…');
      setTimeout(() => router.push('/login'), 1500);
    } catch (e: any) {
      setErr(e.message);
    }
  }

  return (
    <form onSubmit={submit} className="w-full max-w-sm bg-[#11161c] border border-[#232a33] rounded-lg p-6">
      <div className="text-lg font-semibold text-white mb-1">DIEP</div>
      <div className="text-xs text-[#8b95a1] mb-6">Set a new password</div>
      {!token && (
        <div className="text-[#f87171] text-sm mb-3">
          Missing reset token — use the link from &ldquo;Forgot password&rdquo;.
        </div>
      )}
      <label className="block text-xs text-[#8b95a1] mb-1">New password (min 12 characters)</label>
      <input
        type="password"
        value={newPassword}
        onChange={(e) => setNewPassword(e.target.value)}
        className="w-full bg-[#0f1419] border border-[#232a33] rounded px-2 py-1.5 text-sm mb-4 text-white"
      />
      <button
        type="submit"
        disabled={!token || newPassword.length < 12}
        className="w-full bg-[#2563eb] hover:bg-[#1d4ed8] disabled:opacity-50 text-white text-sm rounded px-4 py-2"
      >
        Update password
      </button>
      {msg && <div className="text-[#4ade80] text-sm mt-3">{msg}</div>}
      {err && <div className="text-[#f87171] text-sm mt-3">{err}</div>}
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0b0e12]">
      <Suspense fallback={null}>
        <ResetForm />
      </Suspense>
    </div>
  );
}
