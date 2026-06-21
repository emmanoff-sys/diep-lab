'use client';

import { useState } from 'react';
import dynamic from 'next/dynamic';
import { usePolling } from '@/lib/hooks';
import { postJSON } from '@/lib/api';
import Section, { PageHeader } from '@/components/Section';
import MetricCard from '@/components/MetricCard';
import StatusBadge from '@/components/StatusBadge';
import { Loading } from '@/components/Loading';
import type { OutageMarker, GridGraph } from '@/components/OutageMap';

const OutageMap = dynamic(() => import('@/components/OutageMap'), {
  ssr: false,
  loading: () => <Loading label="Loading map…" />,
});
const FlisrPlanner = dynamic(() => import('@/components/FlisrPlanner'), { ssr: false });
const VoltVarAdvisory = dynamic(() => import('@/components/VoltVarAdvisory'), { ssr: false });

interface OmsCase {
  case_id: string;
  status: string;
  cause: string;
  affected_node_id: string | null;
  affected_node_name?: string | null;
  customers_affected: number;
  detected_at: string;
  restored_at?: string | null;
}
interface Kpis {
  call_volume: number;
  active_outages: number;
  customers_impacted: number;
  avg_restoration_minutes: number;
  saidi_minutes: number;
  saifi: number;
  total_service_points: number;
}

export default function OmsPage() {
  const kpis = usePolling<Kpis>('/oms/kpis?window_hours=24', 10000);
  const cases = usePolling<{ cases: OmsCase[] }>('/oms/cases', 8000);
  const outages = usePolling<{ active: OutageMarker[] }>('/oms/outages', 8000);
  // Read-only grid overlay (ADMS step 1): topology + live switch state, no controls.
  const graph = usePolling<GridGraph>('/topology/graph', 15000);
  const [showGrid, setShowGrid] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  // Call Handler form state.
  const [call, setCall] = useState({ customer_id: '', caller_name: '', caller_phone: '', description: '' });

  async function act(fn: () => Promise<any>, label: string) {
    setBusy(true);
    setMsg(null);
    try {
      await fn();
      setMsg(`${label} ✓`);
      kpis.mutate();
      cases.mutate();
      outages.mutate();
    } catch (e: any) {
      setMsg(`${label} failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }

  const runDetect = () => act(() => postJSON('/oms/detect', {}), 'Detection sweep');
  const submitCall = () =>
    act(async () => {
      await postJSON('/oms/call', {
        customer_id: call.customer_id || null,
        caller_name: call.caller_name || null,
        caller_phone: call.caller_phone || null,
        description: call.description || null,
      });
      setCall({ customer_id: '', caller_name: '', caller_phone: '', description: '' });
    }, 'Call logged');

  // Case status changes are PATCH; api.ts only wraps GET/POST/DELETE, so call
  // the BFF directly here (it forwards the user's JWT either way).
  async function patchStatus(id: string, status: string) {
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch(`/api/diep/oms/cases/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      setMsg(`Case → ${status} ✓`);
      kpis.mutate();
      cases.mutate();
      outages.mutate();
    } catch (e: any) {
      setMsg(`Case → ${status} failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }

  const k = kpis.data;

  return (
    <div>
      <PageHeader title="OMS Dashboard" subtitle="Outage Management — detection, cases, and reliability" />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <MetricCard label="Active outages" value={k ? k.active_outages : '—'} />
        <MetricCard label="Customers impacted" value={k ? k.customers_impacted : '—'} />
        <MetricCard label="Calls (24h)" value={k ? k.call_volume : '—'} />
        <MetricCard label="Avg restoration" value={k ? `${k.avg_restoration_minutes} min` : '—'} />
        <MetricCard label="SAIDI (min)" value={k ? k.saidi_minutes : '—'} sub="placeholder" />
        <MetricCard label="SAIFI" value={k ? k.saifi : '—'} sub="placeholder" />
        <MetricCard label="Service points" value={k ? k.total_service_points : '—'} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <Section
            title="Network operating picture"
            right={
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowGrid((v) => !v)}
                  className={`text-xs px-2 py-1 rounded border ${
                    showGrid
                      ? 'bg-[#1f2937] border-[#3b82f6] text-white'
                      : 'border-[#232a33] text-[#8b95a1] hover:bg-[#11161c]'
                  }`}
                  title="Toggle the read-only grid topology overlay"
                >
                  {showGrid ? '◉ Grid layer' : '◯ Grid layer'}
                </button>
                <button
                  onClick={runDetect}
                  disabled={busy}
                  className="text-xs px-2 py-1 rounded bg-[#2563eb] hover:bg-[#1d4ed8] disabled:opacity-50"
                >
                  Run detection sweep
                </button>
              </div>
            }
          >
            {outages.data ? (
              <OutageMap outages={outages.data.active} grid={graph.data ?? null} showGrid={showGrid} />
            ) : (
              <Loading />
            )}
            {msg && <div className="text-xs text-[#8b95a1] mt-2">{msg}</div>}
          </Section>
        </div>

        <div>
          <Section title="Call Handler">
            <div className="space-y-2 text-sm">
              <input
                placeholder="Customer ID (e.g. CUST-001)"
                value={call.customer_id}
                onChange={(e) => setCall({ ...call, customer_id: e.target.value.trim() })}
                className="w-full bg-[#0f1419] border border-[#232a33] rounded px-2 py-1 text-xs"
              />
              <input
                placeholder="Caller name"
                value={call.caller_name}
                onChange={(e) => setCall({ ...call, caller_name: e.target.value })}
                className="w-full bg-[#0f1419] border border-[#232a33] rounded px-2 py-1 text-xs"
              />
              <input
                placeholder="Caller phone"
                value={call.caller_phone}
                onChange={(e) => setCall({ ...call, caller_phone: e.target.value })}
                className="w-full bg-[#0f1419] border border-[#232a33] rounded px-2 py-1 text-xs"
              />
              <textarea
                placeholder="Description"
                value={call.description}
                onChange={(e) => setCall({ ...call, description: e.target.value })}
                className="w-full bg-[#0f1419] border border-[#232a33] rounded px-2 py-1 text-xs"
                rows={2}
              />
              <button
                onClick={submitCall}
                disabled={busy}
                className="w-full text-xs px-2 py-1.5 rounded bg-[#2563eb] hover:bg-[#1d4ed8] disabled:opacity-50"
              >
                Log customer outage call
              </button>
            </div>
          </Section>
        </div>
      </div>

      <Section
        title="FLISR restoration planner"
        right={<span className="text-[10px] uppercase tracking-wider text-[#8b95a1]">Read-only · decision support</span>}
      >
        <FlisrPlanner grid={graph.data ?? null} outages={outages.data?.active ?? []} />
      </Section>

      <Section
        title="Volt/VAR advisory"
        right={<span className="text-[10px] uppercase tracking-wider text-[#8b95a1]">Read-only · advisory</span>}
      >
        <VoltVarAdvisory grid={graph.data ?? null} />
      </Section>

      <Section title="Outage cases">
        {cases.data ? (
          <table className="w-full text-sm">
            <thead className="text-[#8b95a1] text-xs">
              <tr className="text-left">
                <th className="py-1">Case</th>
                <th>Status</th>
                <th>Cause</th>
                <th>Area</th>
                <th>Customers</th>
                <th>Detected</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {cases.data.cases.map((c) => (
                <tr key={c.case_id} className="border-t border-[#232a33]">
                  <td className="py-1.5 font-mono text-xs">{c.case_id.slice(0, 8)}</td>
                  <td><StatusBadge label={c.status} /></td>
                  <td className="text-xs">{c.cause}</td>
                  <td className="text-xs">{c.affected_node_name || c.affected_node_id}</td>
                  <td>{c.customers_affected}</td>
                  <td className="text-xs text-[#8b95a1]">{new Date(c.detected_at).toLocaleString()}</td>
                  <td className="text-xs space-x-1">
                    {c.status === 'DETECTED' && (
                      <button onClick={() => patchStatus(c.case_id, 'CONFIRMED')} disabled={busy}
                        className="text-[#5aa9e6] hover:underline">Confirm</button>
                    )}
                    {(c.status === 'DETECTED' || c.status === 'CONFIRMED') && (
                      <button onClick={() => patchStatus(c.case_id, 'RESTORED')} disabled={busy}
                        className="text-[#4ade80] hover:underline">Restore</button>
                    )}
                    {c.status !== 'CLOSED' && (
                      <button onClick={() => patchStatus(c.case_id, 'CLOSED')} disabled={busy}
                        className="text-[#8b95a1] hover:underline">Close</button>
                    )}
                  </td>
                </tr>
              ))}
              {cases.data.cases.length === 0 && (
                <tr><td colSpan={7} className="py-3 text-center text-[#8b95a1] text-xs">No outage cases</td></tr>
              )}
            </tbody>
          </table>
        ) : (
          <Loading />
        )}
      </Section>
    </div>
  );
}
