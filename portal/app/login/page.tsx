'use client';

import { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get('next') || '/';
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || `Login failed (${res.status})`);
      }
      router.push(next);
      router.refresh();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="w-full max-w-sm bg-[#11161c] border border-[#232a33] rounded-lg p-6">
      <div className="text-lg font-semibold text-white mb-1">DIEP</div>
      <div className="text-xs text-[#8b95a1] mb-6">Operations Portal sign-in</div>
      <label className="block text-xs text-[#8b95a1] mb-1">Username</label>
      <input
        autoFocus
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        className="w-full bg-[#0f1419] border border-[#232a33] rounded px-2 py-1.5 text-sm mb-3 text-white"
      />
      <label className="block text-xs text-[#8b95a1] mb-1">Password</label>
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="w-full bg-[#0f1419] border border-[#232a33] rounded px-2 py-1.5 text-sm mb-4 text-white"
      />
      <button
        type="submit"
        disabled={busy || !username || !password}
        className="w-full bg-[#2563eb] hover:bg-[#1d4ed8] disabled:opacity-50 text-white text-sm rounded px-4 py-2"
      >
        {busy ? 'Signing in…' : 'Sign in'}
      </button>
      {err && <div className="text-[#f87171] text-sm mt-3">{err}</div>}
      <div className="mt-4 text-xs text-center">
        <a href="/forgot-password" className="text-[#5aa9e6] hover:underline">Forgot password?</a>
      </div>
    </form>
  );
}

export default function LoginPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0b0e12]">
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </div>
  );
}
