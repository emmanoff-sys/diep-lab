'use client';

import { useState } from 'react';
import ControlReadiness from '@/components/ControlReadiness';
import type { GridGraph, GridEdge } from '@/components/OutageMap';
import type { ControlAction, ControlDraft } from '@/lib/controls';
import {
  useWhoami, useControlStatus, useControlActions, useActionDetail,
  affordances, canRequest, canApprove,
  approveAction, rejectAction, executeAction, rollbackAction,
} from '@/lib/controls';

// OC-5 — the operational-controls console: the single governed surface that ties
// the read-only ADMS panels to actuation. It shows the control-plane posture
// (SAFE vs LIVE), lets an operator arm switch operations, and runs every armed
// action through the governed queue (approve / execute / rollback) with an audit
// drawer. Buttons are role-gated client-side AND enforced server-side.

const STATUS_TONE: Record<string, string> = {
  PENDING: 'border-[#f59e0b] text-[#fcd34d]',
  APPROVED: 'border-[#3b82f6] text-[#93c5fd]',
  EXECUTED: 'border-[#22c55e] text-[#86efac]',
  REJECTED: 'border-[#6b7280] text-[#9ca3af]',
  FAILED: 'border-[#ef4444] text-[#fca5a5]',
  ROLLED_BACK: 'border-[#6b7280] text-[#9ca3af]',
};

function Badge({ text, cls }: { text: string; cls: string }) {
  return (
    <span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${cls}`}>{text}</span>
  );
}

export default function OperationalControls({
  grid,
  onArm,
}: {
  grid: GridGraph | null;
  onArm: (d: ControlDraft) => void;
}) {
  const whoami = useWhoami();
  const status = useControlStatus();
  const actions = useControlActions(25);
  const role = whoami.data?.role;
  const me = whoami.data?.principal;

  const [openAudit, setOpenAudit] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const live = !!status.data?.controls_enabled;
  const mayRequest = canRequest(role);
  const switches = (grid?.edges ?? []).filter((e) => e.is_switchable);

  async function run(id: string, fn: () => Promise<any>, label: string) {
    setBusyId(id);
    setMsg(null);
    try {
      await fn();
      setMsg(`${label} ✓`);
      actions.mutate();
    } catch (e: any) {
      const m = String(e?.message || e);
      if (m.includes('403')) setMsg(`${label} refused (403) — ${live ? 'separation of duties / role' : 'operational controls disabled (master flag off)'}.`);
      else if (m.includes('409')) setMsg(`${label} refused (409) — ${m.split(':').slice(1).join(':').trim() || 'state/interlock'}.`);
      else setMsg(`${label} failed: ${m}`);
    } finally {
      setBusyId(null);
    }
  }

  function armSwitch(e: GridEdge) {
    const close = !e.is_closed;
    onArm({
      action_type: 'switch_op',
      target: e.edge_id,
      params: { close },
      summary: `${close ? 'Close' : 'Open'} ${e.edge_id} (${e.from_node} → ${e.to_node})`,
      riskHint: 'high',
      details: [
        { label: 'Edge', value: e.edge_id },
        { label: 'Type', value: e.edge_type },
        { label: 'Current', value: e.is_closed ? 'closed' : 'open' },
        { label: 'Requested', value: close ? 'close' : 'open' },
      ],
    });
  }

  return (
    <div className="space-y-4 text-sm">
      {/* Posture banner — hard SAFE vs LIVE visual state */}
      <div
        className={`rounded-lg border px-3 py-2 flex flex-wrap items-center gap-x-4 gap-y-1 ${
          live ? 'border-[#ef4444] bg-[#1a1113]' : 'border-[#22c55e] bg-[#0f1614]'
        }`}
      >
        <div className="flex items-center gap-2">
          <span className={`text-xs font-bold tracking-wider ${live ? 'text-[#fca5a5]' : 'text-[#86efac]'}`}>
            {live ? '● LIVE — actuation enabled' : '● SAFE — actuation disabled'}
          </span>
        </div>
        <div className="text-[11px] text-[#8b95a1]">
          OC_CONTROLS_ENABLED=<span className="font-mono">{String(live)}</span> · default mode{' '}
          <span className="font-mono">dry_run</span>
        </div>
        <div className="text-[11px] text-[#8b95a1]">
          you: <span className="font-mono text-[#c2c9d1]">{me ?? '—'}</span>{' '}
          <span className="font-mono">{role ?? ''}</span>{' '}
          {mayRequest ? (canApprove(role) ? '(may request + approve)' : '(may request)') : '(read-only)'}
        </div>
        <div className="text-[11px] text-[#8b95a1]">
          high-risk: two-person · low-risk: single operator
        </div>
      </div>

      {/* OC-6 — readiness & safety reporting (audit export, queue state, 24h activity) */}
      <ControlReadiness />

      {/* Switch operations — arm surface (the map overlay is read-only; control is here) */}
      <div>
        <div className="text-[11px] uppercase tracking-wider text-[#8b95a1] mb-1">Switch operations</div>
        {switches.length === 0 ? (
          <div className="text-xs text-[#8b95a1]">No switchable edges in the model.</div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {switches.map((e) => (
              <div key={e.edge_id} className="flex items-center gap-2 bg-[#11161c] border border-[#232a33] rounded px-2 py-1.5">
                <span className="font-mono text-[11px] text-[#c2c9d1]">{e.edge_id}</span>
                <Badge
                  text={e.is_closed ? 'closed' : 'open'}
                  cls={e.is_closed ? 'border-[#22c55e] text-[#86efac]' : 'border-[#ef4444] text-[#fca5a5]'}
                />
                {e.edge_type === 'tie' && <Badge text="tie" cls="border-[#f59e0b] text-[#fcd34d]" />}
                <button
                  disabled={!mayRequest}
                  onClick={() => armSwitch(e)}
                  title={mayRequest ? 'Arm a governed switch operation' : 'operator role or higher required'}
                  className="text-[11px] px-2 py-0.5 rounded border border-[#3b82f6] text-[#93c5fd] hover:bg-[#11203a] disabled:opacity-40"
                >
                  Arm {e.is_closed ? 'open' : 'close'}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Action queue */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <div className="text-[11px] uppercase tracking-wider text-[#8b95a1]">Control action queue</div>
          {msg && <div className="text-[11px] text-[#8b95a1]">{msg}</div>}
        </div>
        <div className="border border-[#232a33] rounded-lg overflow-hidden">
          <table className="w-full text-xs">
            <thead className="text-[#8b95a1] bg-[#0f1419]">
              <tr className="text-left">
                <th className="py-1.5 px-2">Type</th>
                <th>Target</th>
                <th>Mode</th>
                <th>Risk</th>
                <th>Status</th>
                <th>Requested by</th>
                <th>Approved by</th>
                <th className="text-right pr-2">Governed actions</th>
              </tr>
            </thead>
            <tbody>
              {(actions.data?.actions ?? []).map((a) => {
                const aff = affordances(a, role, me);
                const isLive = a.mode === 'live';
                return (
                  <tr
                    key={a.action_id}
                    className={`border-t border-[#232a33] ${isLive ? 'border-l-2 border-l-[#ef4444]' : ''}`}
                  >
                    <td className="py-1.5 px-2 font-mono">{a.action_type}</td>
                    <td className="font-mono text-[#c2c9d1]">{a.target ?? '—'}</td>
                    <td>
                      <Badge
                        text={isLive ? 'live' : 'dry-run'}
                        cls={isLive ? 'border-[#ef4444] text-[#fca5a5]' : 'border-[#6b7280] text-[#9ca3af]'}
                      />
                    </td>
                    <td>
                      <Badge
                        text={a.risk}
                        cls={a.risk === 'high' ? 'border-[#ef4444] text-[#fca5a5]' : 'border-[#22c55e] text-[#86efac]'}
                      />
                    </td>
                    <td><Badge text={a.status} cls={STATUS_TONE[a.status] ?? 'border-[#232a33] text-[#8b95a1]'} /></td>
                    <td className="font-mono text-[#8b95a1]">{a.requested_by}</td>
                    <td className="font-mono text-[#8b95a1]">{a.approved_by ?? '—'}</td>
                    <td className="text-right pr-2 space-x-1 whitespace-nowrap">
                      {aff.approve && (
                        <button disabled={busyId === a.action_id}
                          onClick={() => run(a.action_id, () => approveAction(a.action_id, 'approved via console'), 'Approve')}
                          className="text-[#86efac] hover:underline disabled:opacity-40">Approve</button>
                      )}
                      {aff.reject && (
                        <button disabled={busyId === a.action_id}
                          onClick={() => run(a.action_id, () => rejectAction(a.action_id, 'rejected via console'), 'Reject')}
                          className="text-[#fca5a5] hover:underline disabled:opacity-40">Reject</button>
                      )}
                      {aff.execute && (
                        <button disabled={busyId === a.action_id}
                          onClick={() => run(a.action_id, () => executeAction(a.action_id), isLive ? 'Execute LIVE' : 'Execute dry-run')}
                          className={`${isLive ? 'text-[#fca5a5]' : 'text-[#93c5fd]'} hover:underline disabled:opacity-40`}>
                          {isLive ? 'Execute LIVE' : 'Execute'}
                        </button>
                      )}
                      {aff.rollback && (
                        <button disabled={busyId === a.action_id}
                          onClick={() => run(a.action_id, () => rollbackAction(a.action_id), 'Rollback')}
                          className="text-[#fcd34d] hover:underline disabled:opacity-40">Rollback</button>
                      )}
                      <button
                        onClick={() => setOpenAudit(openAudit === a.action_id ? null : a.action_id)}
                        className="text-[#8b95a1] hover:underline">
                        {openAudit === a.action_id ? 'Hide' : 'Audit'}
                      </button>
                    </td>
                  </tr>
                );
              })}
              {(actions.data?.actions ?? []).length === 0 && (
                <tr><td colSpan={8} className="py-3 text-center text-[#8b95a1]">No control actions yet — arm one above.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        {openAudit && <AuditDrawer actionId={openAudit} />}
      </div>
    </div>
  );
}

function AuditDrawer({ actionId }: { actionId: string }) {
  const detail = useActionDetail(actionId);
  const trail = detail.data?.audit ?? [];
  return (
    <div className="mt-2 border border-[#232a33] rounded-lg p-3 bg-[#0f1419]">
      <div className="text-[11px] uppercase tracking-wider text-[#8b95a1] mb-2">
        Audit trail · <span className="font-mono">{actionId.slice(0, 8)}</span>
      </div>
      {trail.length === 0 ? (
        <div className="text-xs text-[#8b95a1]">Loading…</div>
      ) : (
        <ol className="space-y-1">
          {trail.map((ev, i) => (
            <li key={i} className="flex flex-wrap items-baseline gap-2 text-xs">
              <span className="font-mono text-[#5b6470] w-40">{new Date(ev.at).toLocaleString()}</span>
              <span className="font-mono text-[#c2c9d1] w-24">{ev.event}</span>
              <span className="text-[#8b95a1]">by {ev.actor}</span>
              {ev.detail && Object.keys(ev.detail).length > 0 && (
                <span className="font-mono text-[#5b6470] truncate max-w-[40rem]">{JSON.stringify(ev.detail)}</span>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
