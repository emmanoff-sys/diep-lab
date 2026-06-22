'use client';

import { useState } from 'react';
import {
  useAutomationStatus, useAutomationPolicies, useAutomationEvents, patchPolicy,
  type AutomationPolicy, type PolicyMode,
} from '@/lib/automation';
import { useWhoami, canApprove } from '@/lib/controls';

// P4-4 — closed-loop automation console. Shows the engine posture, lets an
// engineer enable policies and switch recommend/auto (the only writes), and renders
// the automation event feed. Auto-execution stays gated server-side; the UI makes
// the gates and the engine's decisions visible. Read-only for under-privileged roles.

const DECISION_TONE: Record<string, string> = {
  proposed: 'border-[#3b82f6] text-[#93c5fd]',
  executed: 'border-[#22c55e] text-[#86efac]',
  blocked: 'border-[#f59e0b] text-[#fcd34d]',
  failed: 'border-[#ef4444] text-[#fca5a5]',
  tripped: 'border-[#ef4444] text-[#fca5a5]',
  skipped: 'border-[#6b7280] text-[#9ca3af]',
  config: 'border-[#6b7280] text-[#9ca3af]',
};

function Badge({ text, cls, title }: { text: string; cls: string; title?: string }) {
  return <span title={title} className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${cls}`}>{text}</span>;
}

export default function AutomationConsole() {
  const whoami = useWhoami();
  const status = useAutomationStatus();
  const policies = useAutomationPolicies();
  const events = useAutomationEvents(40);
  const mayEdit = canApprove(whoami.data?.role);   // engineer+ may toggle policies
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const auto = !!status.data?.automation_enabled;
  const live = !!status.data?.controls_enabled;

  async function update(p: AutomationPolicy, body: { enabled?: boolean; mode?: PolicyMode; reset_trip?: boolean }, label: string) {
    setBusy(p.policy_id); setMsg(null);
    try {
      await patchPolicy(p.policy_id, body);
      setMsg(`${p.policy_id}: ${label} ✓`);
      policies.mutate(); status.mutate();
    } catch (e: any) {
      const m = String(e?.message || e);
      setMsg(`${p.policy_id}: ${label} failed${m.includes('403') ? ' (engineer role required)' : `: ${m}`}`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4 text-sm">
      {/* Posture banner */}
      <div className={`rounded-lg border px-3 py-2 flex flex-wrap items-center gap-x-4 gap-y-1 ${
        auto ? 'border-[#f59e0b] bg-[#1a1610]' : 'border-[#22c55e] bg-[#0f1614]'}`}>
        <span className={`text-xs font-bold tracking-wider ${auto ? 'text-[#fcd34d]' : 'text-[#86efac]'}`}>
          {auto ? '● AUTOMATION ON' : '● AUTOMATION OFF'}
        </span>
        <span className="text-[11px] text-[#8b95a1]">
          OC_AUTOMATION_ENABLED=<span className="font-mono">{String(auto)}</span> · controls{' '}
          <span className="font-mono">{String(live)}</span>
        </span>
        <span className="text-[11px] text-[#8b95a1]">
          {status.data ? `${status.data.enabled_policies}/${status.data.policies} policies enabled` : '—'}
        </span>
        <span className="text-[11px] text-[#8b95a1]">
          auto-execution needs <span className="font-mono">automation</span> + <span className="font-mono">controls</span> + policy mode <span className="font-mono">auto</span> within bounds
        </span>
        {!auto && (
          <span className="text-[11px] text-[#fcd34d]">engine inert until OC_AUTOMATION_ENABLED is set (env)</span>
        )}
      </div>

      {/* Policies */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <div className="text-[11px] uppercase tracking-wider text-[#8b95a1]">Automation policies</div>
          {msg && <div className="text-[11px] text-[#8b95a1]">{msg}</div>}
        </div>
        <div className="border border-[#232a33] rounded-lg overflow-hidden">
          <table className="w-full text-xs">
            <thead className="text-[#8b95a1] bg-[#0f1419]">
              <tr className="text-left">
                <th className="py-1.5 px-2">Policy</th><th>Kind</th><th>State</th><th>Mode</th><th>Bounds</th>
                <th className="text-right pr-2">Controls</th>
              </tr>
            </thead>
            <tbody>
              {(policies.data?.policies ?? []).map((p) => (
                <tr key={p.policy_id} className={`border-t border-[#232a33] ${p.tripped ? 'bg-[#ef44441a]' : ''}`}>
                  <td className="py-1.5 px-2 font-mono">{p.policy_id}</td>
                  <td className="font-mono text-[#8b95a1]">{p.kind}</td>
                  <td className="space-x-1 whitespace-nowrap">
                    <Badge text={p.enabled ? 'enabled' : 'disabled'} cls={p.enabled ? 'border-[#22c55e] text-[#86efac]' : 'border-[#6b7280] text-[#9ca3af]'} />
                    {p.tripped && <Badge text="tripped" cls="border-[#ef4444] text-[#fca5a5]" title={`${p.consecutive_failures} consecutive failures`} />}
                  </td>
                  <td>
                    <Badge text={p.mode} cls={p.mode === 'auto' ? 'border-[#f59e0b] text-[#fcd34d]' : 'border-[#3b82f6] text-[#93c5fd]'} />
                  </td>
                  <td className="font-mono text-[10px] text-[#8b95a1] max-w-[16rem] truncate" title={JSON.stringify(p.bounds)}>
                    {Object.entries(p.bounds).map(([k, v]) => `${k}=${v}`).join(' ')}
                  </td>
                  <td className="text-right pr-2 space-x-2 whitespace-nowrap">
                    <button disabled={!mayEdit || busy === p.policy_id}
                      onClick={() => update(p, { enabled: !p.enabled }, p.enabled ? 'disabled' : 'enabled')}
                      className="text-[#93c5fd] hover:underline disabled:opacity-40">
                      {p.enabled ? 'Disable' : 'Enable'}
                    </button>
                    <button disabled={!mayEdit || busy === p.policy_id}
                      onClick={() => update(p, { mode: p.mode === 'auto' ? 'recommend' : 'auto' }, `mode ${p.mode === 'auto' ? 'recommend' : 'auto'}`)}
                      className="text-[#fcd34d] hover:underline disabled:opacity-40"
                      title="recommend = propose only; auto = execute within bounds (still flag-gated)">
                      {p.mode === 'auto' ? '→ recommend' : '→ auto'}
                    </button>
                    {p.tripped && (
                      <button disabled={!mayEdit || busy === p.policy_id}
                        onClick={() => update(p, { reset_trip: true }, 'trip reset')}
                        className="text-[#86efac] hover:underline disabled:opacity-40">Reset</button>
                    )}
                  </td>
                </tr>
              ))}
              {(policies.data?.policies ?? []).length === 0 && (
                <tr><td colSpan={6} className="py-3 text-center text-[#8b95a1]">No automation policies</td></tr>
              )}
            </tbody>
          </table>
        </div>
        {!mayEdit && <div className="text-[11px] text-[#8b95a1] mt-1">Read-only — engineer role or higher required to change policies.</div>}
      </div>

      {/* Event feed */}
      <div>
        <div className="text-[11px] uppercase tracking-wider text-[#8b95a1] mb-1">Automation activity</div>
        {(events.data?.events ?? []).length === 0 ? (
          <div className="text-xs text-[#8b95a1] bg-[#0f1419] border border-[#232a33] rounded px-2 py-1.5">
            No automation activity yet — enable a policy (and the engine) to see proposals here.
          </div>
        ) : (
          <ul className="space-y-1">
            {(events.data?.events ?? []).map((e) => (
              <li key={e.event_id} className="flex flex-wrap items-center gap-2 text-xs bg-[#11161c] border border-[#232a33] rounded px-2 py-1.5">
                <span className="font-mono text-[#5b6470] w-36">{new Date(e.at).toLocaleString()}</span>
                <span className="font-mono text-[#c2c9d1]">{e.policy_id}</span>
                <Badge text={e.decision} cls={DECISION_TONE[e.decision] ?? 'border-[#232a33] text-[#8b95a1]'} />
                {e.trigger?.fault_node && <span className="text-[#8b95a1]">fault {e.trigger.fault_node}</span>}
                {e.trigger?.node_id && <span className="text-[#8b95a1]">node {e.trigger.node_id} {e.trigger.direction}</span>}
                {e.trigger?.der_id && <span className="font-mono text-[#8b95a1]">{e.trigger.der_id}</span>}
                {e.action_id && <span className="font-mono text-[#5b6470]" title={e.action_id}>act {e.action_id.slice(0, 8)}</span>}
                {e.detail?.out_of_bounds && <span className="text-[#fcd34d]">bounds: {String(e.detail.out_of_bounds)}</span>}
                {e.detail?.error && <span className="text-[#fca5a5]">{String(e.detail.error).slice(0, 80)}</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
