'use client';

import { useState } from 'react';
import { usePolling } from '@/lib/hooks';
import { postJSON, delJSON } from '@/lib/api';
import type { Asset } from '@/lib/types';
import Section, { PageHeader } from '@/components/Section';
import StatusBadge from '@/components/StatusBadge';
import { Loading } from '@/components/Loading';
import { CONSOLES } from '@/lib/grafana';

type Whoami = { principal: string; role: string };
type PortalUser = { username: string; role: string; tenant: string | null; created_at: string };
type AuditEvent = {
  id: string; ts: string; principal: string; role: string | null; action: string;
  resource: string | null; site: string | null; request_id: string | null; result: string;
};

export default function AdministrationPage() {
  const whoami = usePolling<Whoami>('/auth/whoami', 30000);
  const isAdmin = whoami.data?.role === 'admin';

  const devices = usePolling<{ assets: Asset[] }>('/assets', 15000);
  const apiHealth = usePolling<{ status: string }>('/health', 15000);
  const users = usePolling<{ users: PortalUser[] }>(isAdmin ? '/auth/users' : null, 15000);
  const auditLog = usePolling<{ events: AuditEvent[] }>(isAdmin ? '/audit/events?limit=25' : null, 15000);

  const [form, setForm] = useState({ device_id: '', device_type: 'battery', location: '', site_name: 'Abuja Site A', status: 'ONLINE' });
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const [userForm, setUserForm] = useState({ username: '', password: '', role: 'viewer', tenant: '' });
  const [userMsg, setUserMsg] = useState<string | null>(null);
  const [userErr, setUserErr] = useState<string | null>(null);

  async function register() {
    setMsg(null);
    setErr(null);
    try {
      await postJSON('/assets', { ...form, metadata: {} });
      setMsg(`Registered ${form.device_id}`);
      devices.mutate();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function createUser() {
    setUserMsg(null);
    setUserErr(null);
    try {
      await postJSON('/auth/users', { ...userForm, tenant: userForm.tenant || null });
      setUserMsg(`Created ${userForm.username}`);
      setUserForm({ username: '', password: '', role: 'viewer', tenant: '' });
      users.mutate();
    } catch (e: any) {
      setUserErr(e.message);
    }
  }

  async function removeUser(username: string) {
    setUserMsg(null);
    setUserErr(null);
    try {
      await delJSON(`/auth/users/${encodeURIComponent(username)}`);
      setUserMsg(`Removed ${username}`);
      users.mutate();
    } catch (e: any) {
      setUserErr(e.message);
    }
  }

  return (
    <div>
      <PageHeader title="Administration" subtitle="Registry, system status, consoles" />

      <div className="grid lg:grid-cols-2 gap-4">
        <Section
          title="Backend status"
          right={<StatusBadge label={apiHealth.data?.status === 'UP' ? 'ONLINE' : 'OFFLINE'} />}
        >
          <div className="text-sm text-[#8b95a1]">DIEP API: {apiHealth.data?.status || 'unknown'}</div>
          <div className="mt-3 grid grid-cols-2 gap-2">
            {CONSOLES.map((c) => (
              <a
                key={c.name}
                href={c.url}
                target="_blank"
                rel="noreferrer"
                className="border border-[#232a33] rounded p-2 hover:bg-[#11161c]"
              >
                <div className="text-sm text-[#5aa9e6]">↗ {c.name}</div>
                <div className="text-xs text-[#8b95a1]">{c.note}</div>
              </a>
            ))}
          </div>
        </Section>

        <Section title="Register asset">
          <div className="grid gap-2">
            <input
              placeholder="device_id"
              value={form.device_id}
              onChange={(e) => setForm({ ...form, device_id: e.target.value })}
              className="bg-[#0f1419] border border-[#232a33] rounded px-2 py-1.5 text-sm"
            />
            <select
              value={form.device_type}
              onChange={(e) => setForm({ ...form, device_type: e.target.value })}
              className="bg-[#0f1419] border border-[#232a33] rounded px-2 py-1.5 text-sm"
            >
              {['battery', 'solar_inverter', 'ev_charger', 'microgrid', 'smartmeter'].map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <input
              placeholder="location"
              value={form.location}
              onChange={(e) => setForm({ ...form, location: e.target.value })}
              className="bg-[#0f1419] border border-[#232a33] rounded px-2 py-1.5 text-sm"
            />
            <input
              placeholder="site_name"
              value={form.site_name}
              onChange={(e) => setForm({ ...form, site_name: e.target.value })}
              className="bg-[#0f1419] border border-[#232a33] rounded px-2 py-1.5 text-sm"
            />
            <button
              onClick={register}
              disabled={!form.device_id}
              className="bg-[#2563eb] hover:bg-[#1d4ed8] disabled:opacity-50 text-white text-sm rounded px-4 py-1.5 mt-1"
            >
              Register
            </button>
            {msg && <div className="text-[#4ade80] text-sm">{msg}</div>}
            {err && <div className="text-[#f87171] text-sm">{err}</div>}
          </div>
        </Section>
      </div>

      <Section title="Device registry">
        {devices.data ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[#8b95a1] text-left">
                <th className="py-2 px-2">Device</th>
                <th className="py-2 px-2">Type</th>
                <th className="py-2 px-2">Location</th>
                <th className="py-2 px-2">Site</th>
                <th className="py-2 px-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {devices.data.assets.map((a) => (
                <tr key={a.device_id} className="border-t border-[#232a33]">
                  <td className="py-2 px-2">{a.device_id}</td>
                  <td className="py-2 px-2 text-[#c2c9d1]">{a.device_type}</td>
                  <td className="py-2 px-2 text-[#8b95a1]">{a.location || '—'}</td>
                  <td className="py-2 px-2 text-[#8b95a1]">{a.site_name || '—'}</td>
                  <td className="py-2 px-2"><StatusBadge label={a.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Loading />
        )}
      </Section>

      {isAdmin && (
        <>
          <Section title="Users (Administrator only)">
            <div className="grid lg:grid-cols-2 gap-4">
              <div className="grid gap-2">
                <input
                  placeholder="username"
                  value={userForm.username}
                  onChange={(e) => setUserForm({ ...userForm, username: e.target.value })}
                  className="bg-[#0f1419] border border-[#232a33] rounded px-2 py-1.5 text-sm"
                />
                <input
                  placeholder="password (min 12 chars)"
                  type="password"
                  value={userForm.password}
                  onChange={(e) => setUserForm({ ...userForm, password: e.target.value })}
                  className="bg-[#0f1419] border border-[#232a33] rounded px-2 py-1.5 text-sm"
                />
                <select
                  value={userForm.role}
                  onChange={(e) => setUserForm({ ...userForm, role: e.target.value })}
                  className="bg-[#0f1419] border border-[#232a33] rounded px-2 py-1.5 text-sm"
                >
                  {['viewer', 'operator', 'engineer', 'admin'].map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
                <input
                  placeholder="tenant (optional)"
                  value={userForm.tenant}
                  onChange={(e) => setUserForm({ ...userForm, tenant: e.target.value })}
                  className="bg-[#0f1419] border border-[#232a33] rounded px-2 py-1.5 text-sm"
                />
                <button
                  onClick={createUser}
                  disabled={!userForm.username || userForm.password.length < 12}
                  className="bg-[#2563eb] hover:bg-[#1d4ed8] disabled:opacity-50 text-white text-sm rounded px-4 py-1.5 mt-1"
                >
                  Create user
                </button>
                {userMsg && <div className="text-[#4ade80] text-sm">{userMsg}</div>}
                {userErr && <div className="text-[#f87171] text-sm">{userErr}</div>}
              </div>

              {users.data ? (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-[#8b95a1] text-left">
                      <th className="py-2 px-2">Username</th>
                      <th className="py-2 px-2">Role</th>
                      <th className="py-2 px-2">Tenant</th>
                      <th className="py-2 px-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {users.data.users.map((u) => (
                      <tr key={u.username} className="border-t border-[#232a33]">
                        <td className="py-2 px-2">{u.username}</td>
                        <td className="py-2 px-2 text-[#c2c9d1]">{u.role}</td>
                        <td className="py-2 px-2 text-[#8b95a1]">{u.tenant || '—'}</td>
                        <td className="py-2 px-2 text-right">
                          <button onClick={() => removeUser(u.username)} className="text-[#f87171] hover:underline text-xs">
                            Remove
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <Loading />
              )}
            </div>
          </Section>

          <Section title="Audit log (Administrator only, most recent 25)">
            {auditLog.data ? (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[#8b95a1] text-left">
                    <th className="py-2 px-2">Time</th>
                    <th className="py-2 px-2">Principal</th>
                    <th className="py-2 px-2">Action</th>
                    <th className="py-2 px-2">Resource</th>
                    <th className="py-2 px-2">Site</th>
                    <th className="py-2 px-2">Result</th>
                    <th className="py-2 px-2">Request ID</th>
                  </tr>
                </thead>
                <tbody>
                  {auditLog.data.events.map((e) => (
                    <tr key={e.id} className="border-t border-[#232a33]">
                      <td className="py-2 px-2 text-[#8b95a1]">{new Date(e.ts).toLocaleString()}</td>
                      <td className="py-2 px-2">{e.principal}{e.role ? ` (${e.role})` : ''}</td>
                      <td className="py-2 px-2 text-[#c2c9d1]">{e.action}</td>
                      <td className="py-2 px-2 text-[#8b95a1]">{e.resource || '—'}</td>
                      <td className="py-2 px-2 text-[#8b95a1]">{e.site || '—'}</td>
                      <td className="py-2 px-2"><StatusBadge label={e.result.toUpperCase()} /></td>
                      <td className="py-2 px-2 text-[#8b95a1] font-mono text-xs">{e.request_id || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <Loading />
            )}
          </Section>
        </>
      )}
    </div>
  );
}
