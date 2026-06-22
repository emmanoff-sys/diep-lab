'use client';

import { useMemo, useState } from 'react';
import { postJSON } from '@/lib/api';
import type { GridGraph, GridEdge, OutageMarker } from '@/components/OutageMap';
import type { ControlDraft } from '@/lib/controls';

// ADMS step 2 — read-only FLISR planning panel.
// Calls POST /dms/flisr/simulate with execute=false ONLY. It plans on a copy of
// the network model server-side and never operates a switch; the sole server
// write is the simulation's own audit record (executed=false), which is why this
// is operator-initiated (a click) rather than polled. No switching/execution
// capability is exposed here — there is deliberately no execute button.

interface FlisrPlan {
  event_id: string;
  fault_node: string;
  fault_edge: string | null;
  executed: boolean;
  isolated_edges: string[];
  restored_edges: string[];
  customers_lost: number;
  customers_restored: number;
  customers_still_out: number;
  steps: string[];
}

function edgeLabel(edges: GridEdge[], id: string): string {
  const e = edges.find((x) => x.edge_id === id);
  return e ? `${e.from_node} → ${e.to_node}` : '';
}

function Chip({ text, tone }: { text: string; tone: 'open' | 'close' | 'muted' }) {
  const styles =
    tone === 'open'
      ? 'border-[#ef4444] text-[#fca5a5] bg-[#ef44441a]'
      : tone === 'close'
      ? 'border-[#22c55e] text-[#86efac] bg-[#22c55e1a]'
      : 'border-[#232a33] text-[#8b95a1]';
  return <span className={`inline-block font-mono text-[11px] px-2 py-0.5 rounded border ${styles}`}>{text}</span>;
}

export default function FlisrPlanner({
  grid,
  outages,
  onArm,
}: {
  grid: GridGraph | null;
  outages: OutageMarker[];
  onArm?: (d: ControlDraft) => void; // OC-5: when provided, expose a governed "Arm" affordance
}) {
  const nodes = grid?.nodes ?? [];
  const edges = grid?.edges ?? [];

  // Fault options: anything downstream of the source (exclude the substation).
  const options = useMemo(
    () => nodes.filter((n) => n.node_type !== 'substation').map((n) => ({ id: n.node_id, name: n.name })),
    [nodes],
  );
  const defaultFault = useMemo(() => {
    const outNode = (outages || []).find((o) => o.affected_node_id)?.affected_node_id;
    if (outNode && options.some((o) => o.id === outNode)) return outNode;
    if (options.some((o) => o.id === 'TX-01')) return 'TX-01';
    return options[0]?.id ?? '';
  }, [options, outages]);

  const [faultNode, setFaultNode] = useState<string>('');
  const [plan, setPlan] = useState<FlisrPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selected = faultNode || defaultFault;

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      // execute=false: plan only — no switching, no live state change.
      const p = await postJSON<FlisrPlan>('/dms/flisr/simulate', { fault_node: selected, execute: false });
      setPlan(p);
    } catch (e: any) {
      const msg = String(e?.message || e);
      if (msg.includes('403')) setError('FLISR planning requires operator role or higher.');
      else if (msg.includes('409')) setError('No upstream switch can isolate a fault at this location.');
      else if (msg.includes('404') || msg.includes('422')) setError('Pick a valid fault location.');
      else setError(msg);
      setPlan(null);
    } finally {
      setBusy(false);
    }
  }

  const lost = plan?.customers_lost ?? 0;
  const restored = plan?.customers_restored ?? 0;
  const remaining = plan?.customers_still_out ?? 0;
  const pct = lost > 0 ? Math.round((100 * restored) / lost) : restored > 0 ? 100 : 0;

  // OC-5: hand the displayed plan to the control console to be armed as a governed
  // `flisr` action. The server re-plans authoritatively at request/execute time.
  function arm() {
    if (!plan || !onArm) return;
    onArm({
      action_type: 'flisr',
      target: plan.fault_node,
      params: { fault_node: plan.fault_node },
      summary: `FLISR restoration for fault at ${plan.fault_node}`,
      riskHint: 'high',
      details: [
        { label: 'Fault', value: plan.fault_node },
        { label: 'Restored', value: String(restored) },
        { label: 'Open', value: plan.isolated_edges.join(', ') || 'none' },
        { label: 'Close ties', value: plan.restored_edges.join(', ') || 'none' },
      ],
    });
  }

  return (
    <div className="space-y-3 text-sm">
      <div className="text-[11px] text-[#8b95a1] bg-[#0f1419] border border-[#232a33] rounded px-2 py-1.5">
        Read-only decision support. Generates a plan via <span className="font-mono">/dms/flisr/simulate</span> with{' '}
        <span className="font-mono">execute=false</span> — no switches are operated and no live switch state changes.
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <label className="text-xs text-[#8b95a1]">
          Fault location
          <select
            value={selected}
            onChange={(e) => setFaultNode(e.target.value)}
            className="mt-1 block bg-[#0f1419] border border-[#232a33] rounded px-2 py-1 text-xs min-w-[14rem]"
          >
            {options.map((o) => (
              <option key={o.id} value={o.id}>
                {o.id}
                {o.name ? ` — ${o.name}` : ''}
              </option>
            ))}
          </select>
        </label>
        <button
          onClick={generate}
          disabled={busy || !selected}
          className="text-xs px-3 py-1.5 rounded bg-[#2563eb] hover:bg-[#1d4ed8] disabled:opacity-50"
        >
          {busy ? 'Planning…' : 'Generate plan'}
        </button>
      </div>

      {error && <div className="text-xs text-[#fca5a5]">{error}</div>}

      {plan && (
        <div data-testid="flisr-plan" className="border border-[#232a33] rounded-lg p-3 bg-[#11161c]">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm font-semibold text-white">Recommended FLISR Plan</div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded bg-[#1f2937] text-[#93c5fd] border border-[#3b82f6]">
                Plan only · not executed
              </span>
              {onArm && (
                <button
                  onClick={arm}
                  title="Arm this plan as a governed FLISR action (request → approve → execute)"
                  className="text-[11px] px-2 py-0.5 rounded border border-[#f59e0b] text-[#fcd34d] hover:bg-[#1f1a0f]"
                >
                  ⚡ Arm FLISR action
                </button>
              )}
            </div>
          </div>

          {/* Affected feeder / section */}
          <div className="text-xs text-[#c2c9d1] mb-3">
            <span className="text-[#8b95a1]">Affected section: </span>
            faulted at <span className="font-mono">{plan.fault_node}</span>
            {plan.isolated_edges.length > 0 && (
              <>
                {' '}— isolated by opening <span className="font-mono">{plan.isolated_edges.join(', ')}</span>
              </>
            )}
          </div>

          {/* Metrics */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
            <Metric label="Customers restored" value={restored} accent="#4ade80" />
            <Metric label="Remaining interrupted" value={remaining} accent={remaining > 0 ? '#fca5a5' : '#8b95a1'} />
            <Metric label="Restoration" value={`${pct}%`} accent="#5aa9e6" />
            <Metric label="Customers in section" value={lost} accent="#c2c9d1" />
          </div>

          {/* Switch operations */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
            <div>
              <div className="text-[11px] uppercase tracking-wider text-[#8b95a1] mb-1">Switches to open</div>
              <div className="flex flex-wrap gap-1.5">
                {plan.isolated_edges.length ? (
                  plan.isolated_edges.map((id) => <Chip key={id} text={id} tone="open" />)
                ) : (
                  <span className="text-xs text-[#8b95a1]">none</span>
                )}
              </div>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-wider text-[#8b95a1] mb-1">
                Tie switches to close
              </div>
              <div className="flex flex-wrap gap-1.5">
                {plan.restored_edges.length ? (
                  plan.restored_edges.map((id) => <Chip key={id} text={id} tone="close" />)
                ) : (
                  <span className="text-xs text-[#8b95a1]">none</span>
                )}
              </div>
            </div>
          </div>

          {/* Operator-facing rationale */}
          <div>
            <div className="text-[11px] uppercase tracking-wider text-[#8b95a1] mb-1">Why these actions</div>
            <ul className="space-y-1 text-xs text-[#c2c9d1]">
              {plan.isolated_edges.map((id) => (
                <li key={`why-open-${id}`} className="flex gap-2">
                  <Chip text="OPEN" tone="open" />
                  <span>
                    <span className="font-mono">{id}</span> ({edgeLabel(edges, id)}) — isolates the faulted section at{' '}
                    <span className="font-mono">{plan.fault_node}</span> from its source, de-energizing the fault before
                    any back-feed so it can&apos;t be re-energized.
                  </span>
                </li>
              ))}
              {plan.restored_edges.map((id) => (
                <li key={`why-close-${id}`} className="flex gap-2">
                  <Chip text="CLOSE" tone="close" />
                  <span>
                    <span className="font-mono">{id}</span> ({edgeLabel(edges, id)}) — closes this normally-open tie to
                    back-feed the healthy, de-energized customers from an alternate source. Chosen because it restores
                    load <em>without</em> re-energizing the faulted node.
                  </span>
                </li>
              ))}
              {plan.restored_edges.length === 0 && (
                <li className="flex gap-2">
                  <Chip text="HOLD" tone="muted" />
                  <span>
                    No normally-open tie can back-feed this section without re-energizing the fault — affected customers
                    remain interrupted until the fault is repaired. (FLISR will not re-energize a faulted node.)
                  </span>
                </li>
              )}
            </ul>
          </div>

          {/* Authoritative plan sequence from the engine */}
          {plan.steps?.length > 0 && (
            <details className="mt-3">
              <summary className="text-[11px] uppercase tracking-wider text-[#8b95a1] cursor-pointer">
                Plan sequence (engine)
              </summary>
              <ol className="list-decimal list-inside text-xs text-[#8b95a1] mt-1 space-y-0.5">
                {plan.steps.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ol>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, accent }: { label: string; value: number | string; accent: string }) {
  return (
    <div className="bg-[#0f1419] border border-[#232a33] rounded px-2 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-[#8b95a1]">{label}</div>
      <div className="text-lg font-semibold" style={{ color: accent }}>
        {value}
      </div>
    </div>
  );
}
