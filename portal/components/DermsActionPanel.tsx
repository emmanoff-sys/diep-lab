'use client';

import { useState } from 'react';
import { postJSON } from '@/lib/api';

type Field = { name: string; label: string; type: 'number' | 'text'; default?: any };

const ACTIONS: { key: string; label: string; endpoint: string; fields: Field[] }[] = [
  {
    key: 'battery_dispatch',
    label: 'Battery Dispatch',
    endpoint: '/derms/battery_dispatch',
    fields: [
      { name: 'device_id', label: 'Device ID (optional)', type: 'text', default: 'BAT001' },
      { name: 'target_soc', label: 'Target SOC %', type: 'number', default: 80 },
      { name: 'max_power_kw', label: 'Max power kW (optional)', type: 'number' },
    ],
  },
  {
    key: 'peak_shaving',
    label: 'Peak Shaving',
    endpoint: '/derms/peak_shaving',
    fields: [
      { name: 'site_name', label: 'Site (optional)', type: 'text', default: 'Abuja Site A' },
      { name: 'reduction_kw', label: 'Reduction kW', type: 'number', default: 5 },
    ],
  },
  {
    key: 'demand_response',
    label: 'Demand Response',
    endpoint: '/derms/demand_response',
    fields: [
      { name: 'site_name', label: 'Site (optional)', type: 'text', default: 'Abuja Site A' },
      { name: 'event_duration_minutes', label: 'Duration min', type: 'number', default: 30 },
      { name: 'target_reduction_kw', label: 'Target reduction kW', type: 'number', default: 5 },
    ],
  },
  {
    key: 'load_optimization',
    label: 'Load Optimization',
    endpoint: '/derms/load_optimization',
    fields: [
      { name: 'site_name', label: 'Site (optional)', type: 'text', default: 'Abuja Site A' },
      { name: 'objective', label: 'Objective', type: 'text', default: 'maximize_solar' },
      { name: 'optimization_horizon_hours', label: 'Horizon hours', type: 'number', default: 1 },
    ],
  },
];

export default function DermsActionPanel({ onSubmitted }: { onSubmitted?: () => void }) {
  const [active, setActive] = useState(ACTIONS[0].key);
  const [values, setValues] = useState<Record<string, any>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const action = ACTIONS.find((a) => a.key === active)!;

  function val(f: Field) {
    return values[f.name] ?? f.default ?? '';
  }

  async function submit() {
    setBusy(true);
    setMsg(null);
    setErr(null);
    const body: Record<string, any> = {};
    for (const f of action.fields) {
      let v = values[f.name] ?? f.default;
      if (v === '' || v === undefined || v === null) continue;
      body[f.name] = f.type === 'number' ? Number(v) : v;
    }
    try {
      const res: any = await postJSON(action.endpoint, body);
      setMsg(`Request ${res.request_id || ''} → ${res.command?.status || 'submitted'}`);
      onSubmitted?.();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="flex flex-wrap gap-2 mb-4">
        {ACTIONS.map((a) => (
          <button
            key={a.key}
            onClick={() => {
              setActive(a.key);
              setValues({});
              setMsg(null);
              setErr(null);
            }}
            className={`text-sm rounded px-3 py-1.5 border ${
              active === a.key
                ? 'border-[#3b82f6] bg-[#1d2733] text-white'
                : 'border-[#232a33] text-[#c2c9d1] hover:bg-[#11161c]'
            }`}
          >
            {a.label}
          </button>
        ))}
      </div>

      <div className="grid gap-3">
        {action.fields.map((f) => (
          <div key={f.name}>
            <label className="block text-xs text-[#8b95a1] mb-1">{f.label}</label>
            <input
              type={f.type}
              value={val(f)}
              onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
              className="w-full bg-[#0f1419] border border-[#232a33] rounded px-2 py-1.5 text-sm"
            />
          </div>
        ))}
      </div>

      <button
        onClick={submit}
        disabled={busy}
        className="mt-4 bg-[#2563eb] hover:bg-[#1d4ed8] disabled:opacity-50 text-white text-sm rounded px-4 py-1.5"
      >
        {busy ? 'Submitting…' : `Submit ${action.label}`}
      </button>

      {msg && <div className="text-[#4ade80] text-sm mt-3">{msg}</div>}
      {err && <div className="text-[#f87171] text-sm mt-3">{err}</div>}
    </div>
  );
}
