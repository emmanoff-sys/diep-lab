'use client';

import { useMemo, useState } from 'react';
import { usePolling } from '@/lib/hooks';
import type { GridGraph } from '@/components/OutageMap';
import type { ControlDraft } from '@/lib/controls';

// ADMS step 3 — Volt/VAR advisory panel (read-only).
// Reads existing DMS GETs only: /dms/state_estimation and
// /dms/voltvar/recommendations. Both are read-only and mutate nothing. There is
// deliberately no execute/control affordance — every recommendation is advisory.

interface EstNode {
  node_id: string;
  node_type: string;
  name: string | null;
  energized: boolean;
  monitored: boolean;
  measured_voltage: number | null;
  measured_power_kw: number | null;
  downstream_load_kw: number;
  estimated_voltage_pu: number;
}
interface StateEstimation {
  method: string;
  monitored_nodes: number;
  total_nodes: number;
  nodes: EstNode[];
}
interface VVRec {
  node_id: string;
  name: string | null;
  issue: string;
  direction: string; // raise | lower
  recommended_action: string;
}
interface VoltVar {
  bands: { lv_volts: [number, number]; pu: [number, number] };
  violations: number;
  recommendations: VVRec[];
  note: string;
}

interface DerAsset {
  der_id: string;
  der_type: string;
  rated_kw: number | null;
  controllable: boolean;
  output_kw: number | null;
  online: boolean;
}

export default function VoltVarAdvisory({
  grid,
  onArm,
}: {
  grid: GridGraph | null;
  onArm?: (d: ControlDraft) => void; // OC-5: when provided, expose a governed dispatch surface
}) {
  const se = usePolling<StateEstimation>('/dms/state_estimation', 12000);
  const vv = usePolling<VoltVar>('/dms/voltvar/recommendations', 12000);

  // Resolve each node to its feeder by walking parent_id up the topology graph.
  const feederOf = useMemo(() => {
    const byId = new Map((grid?.nodes ?? []).map((n) => [n.node_id, n]));
    return (nodeId: string): string => {
      let cur = byId.get(nodeId);
      let guard = 0;
      while (cur && guard++ < 50) {
        if (cur.node_type === 'feeder') return cur.node_id;
        const parent = (cur as any).parent_id as string | null;
        if (!parent) break;
        cur = byId.get(parent);
      }
      return '—';
    };
  }, [grid]);

  const recById = useMemo(
    () => new Set((vv.data?.recommendations ?? []).map((r) => r.node_id)),
    [vv.data],
  );

  const bands = vv.data?.bands;
  const energized = (se.data?.nodes ?? []).filter((n) => n.energized);
  const deEnergized = (se.data?.nodes ?? []).length - energized.length;

  return (
    <div data-testid="voltvar-advisory" className="space-y-3 text-sm">
      <div className="text-[11px] text-[#8b95a1] bg-[#0f1419] border border-[#232a33] rounded px-2 py-1.5">
        <span className="text-[#fcd34d] font-semibold">Advisory only.</span> Derived from{' '}
        <span className="font-mono">/dms/state_estimation</span> and{' '}
        <span className="font-mono">/dms/voltvar/recommendations</span> — rule-based on measured/estimated voltage.
        No control action is taken and no state is changed.
      </div>

      {/* OC-5: governed Volt/VAR dispatch surface (advisory above stays read-only) */}
      {onArm && <VoltVarDispatch onArm={onArm} />}

      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <Metric label="Violations" value={vv.data ? vv.data.violations : '—'} accent={vv.data?.violations ? '#fca5a5' : '#4ade80'} />
        <Metric label="Monitored nodes" value={se.data ? `${se.data.monitored_nodes}/${se.data.total_nodes}` : '—'} accent="#c2c9d1" />
        <Metric label="LV band" value={bands ? `${bands.lv_volts[0]}–${bands.lv_volts[1]} V` : '—'} accent="#5aa9e6" />
        <Metric label="pu band" value={bands ? `${bands.pu[0]}–${bands.pu[1]}` : '—'} accent="#5aa9e6" />
      </div>

      {/* Recommendations */}
      <div>
        <div className="text-[11px] uppercase tracking-wider text-[#8b95a1] mb-1">Volt/VAR recommendations</div>
        {!vv.data ? (
          <div className="text-xs text-[#8b95a1]">Loading…</div>
        ) : vv.data.recommendations.length === 0 ? (
          <div className="text-xs text-[#86efac] bg-[#0f1419] border border-[#232a33] rounded px-2 py-1.5">
            No voltage violations — all monitored and estimated voltages are within band.
          </div>
        ) : (
          <ul className="space-y-1.5">
            {vv.data.recommendations.map((r) => (
              <li key={r.node_id} className="flex flex-wrap items-center gap-2 text-xs bg-[#11161c] border border-[#232a33] rounded px-2 py-1.5">
                <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-[#1f2937] text-[#fcd34d] border border-[#a16207]">
                  Advisory
                </span>
                <span className={`text-[10px] uppercase px-1.5 py-0.5 rounded border ${
                  r.direction === 'raise' ? 'border-[#5aa9e6] text-[#93c5fd]' : 'border-[#f59e0b] text-[#fcd34d]'
                }`}>
                  {r.direction}
                </span>
                <span className="font-mono">{r.node_id}</span>
                <span className="text-[#8b95a1]">feeder {feederOf(r.node_id)}</span>
                <span className="text-[#c2c9d1]">{r.issue}</span>
                <span className="text-[#8b95a1]">→ suggest: {r.recommended_action}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* State-estimation voltages */}
      <div>
        <div className="text-[11px] uppercase tracking-wider text-[#8b95a1] mb-1">State-estimation voltages</div>
        {!se.data ? (
          <div className="text-xs text-[#8b95a1]">Loading…</div>
        ) : (
          <table className="w-full text-xs">
            <thead className="text-[#8b95a1]">
              <tr className="text-left">
                <th className="py-1">Node</th>
                <th>Feeder</th>
                <th>Type</th>
                <th>Source</th>
                <th>Voltage</th>
                <th>Downstream load</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {energized.map((n) => {
                const violation = recById.has(n.node_id);
                const measured = n.monitored && n.measured_voltage != null;
                return (
                  <tr key={n.node_id} className={`border-t border-[#232a33] ${violation ? 'bg-[#ef44441a]' : ''}`}>
                    <td className="py-1 font-mono">{n.node_id}</td>
                    <td className="text-[#8b95a1]">{feederOf(n.node_id)}</td>
                    <td className="text-[#8b95a1]">{n.node_type}</td>
                    <td className="text-[#8b95a1]">{measured ? 'Measured' : 'Estimated'}</td>
                    <td className={violation ? 'text-[#fca5a5]' : 'text-[#c2c9d1]'}>
                      {measured ? `${n.measured_voltage} V` : `${n.estimated_voltage_pu} pu`}
                    </td>
                    <td className="text-[#8b95a1]">{n.downstream_load_kw} kW</td>
                    <td>
                      {violation ? (
                        <span className="text-[#fca5a5]">out of band</span>
                      ) : (
                        <span className="text-[#86efac]">in band</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {deEnergized > 0 && (
          <div className="text-[11px] text-[#8b95a1] mt-1">
            {deEnergized} de-energized node(s) excluded from Volt/VAR evaluation.
          </div>
        )}
        {se.data && <div className="text-[10px] text-[#5b6470] mt-1">Method: {se.data.method}</div>}
      </div>
    </div>
  );
}

function Metric({ label, value, accent }: { label: string; value: number | string; accent: string }) {
  return (
    <div className="bg-[#0f1419] border border-[#232a33] rounded px-2 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-[#8b95a1]">{label}</div>
      <div className="text-lg font-semibold" style={{ color: accent }}>{value}</div>
    </div>
  );
}

// OC-5 — Volt/VAR dispatch control surface. Lists controllable DERs and lets an
// operator arm a governed `voltvar_dispatch` (setpoint within [0, rated]; a swing
// beyond the server's rate-limit is classified high-risk → two-person). Arming
// only *requests* the action; execution is governed + flag-gated in the console.
function VoltVarDispatch({ onArm }: { onArm: (d: ControlDraft) => void }) {
  const ders = usePolling<{ der_assets: DerAsset[] }>('/der/assets', 12000);
  const [sel, setSel] = useState<string>('');
  const [sp, setSp] = useState<string>('');

  const controllable = (ders.data?.der_assets ?? []).filter((d) => d.controllable);
  const chosen = controllable.find((d) => d.der_id === (sel || controllable[0]?.der_id));

  function arm() {
    if (!chosen) return;
    const setpoint = Number(sp);
    if (!Number.isFinite(setpoint)) return;
    onArm({
      action_type: 'voltvar_dispatch',
      target: chosen.der_id,
      params: { setpoint_kw: setpoint },
      summary: `Set ${chosen.der_id} (${chosen.der_type}) to ${setpoint} kW`,
      // best-effort hint; server classifies by actual swing vs fresh telemetry.
      riskHint: chosen.output_kw != null && Math.abs(setpoint - chosen.output_kw) > 10 ? 'high' : 'low',
      details: [
        { label: 'DER', value: chosen.der_id },
        { label: 'Now', value: chosen.output_kw != null ? `${chosen.output_kw} kW` : 'stale' },
        { label: 'Target', value: `${setpoint} kW` },
        { label: 'Rated', value: chosen.rated_kw != null ? `${chosen.rated_kw} kW` : '—' },
      ],
    });
  }

  return (
    <div className="border border-[#232a33] rounded-lg p-3 bg-[#11161c]">
      <div className="flex items-center justify-between mb-2">
        <div className="text-[11px] uppercase tracking-wider text-[#8b95a1]">Volt/VAR dispatch (governed)</div>
        <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded bg-[#1f2937] text-[#fcd34d] border border-[#a16207]">
          Arm only · execution governed
        </span>
      </div>
      {controllable.length === 0 ? (
        <div className="text-xs text-[#8b95a1]">No controllable DERs.</div>
      ) : (
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-xs text-[#8b95a1]">
            DER
            <select
              value={sel || controllable[0]?.der_id}
              onChange={(e) => setSel(e.target.value)}
              className="mt-1 block bg-[#0f1419] border border-[#232a33] rounded px-2 py-1 text-xs min-w-[12rem]"
            >
              {controllable.map((d) => (
                <option key={d.der_id} value={d.der_id}>
                  {d.der_id} — {d.der_type}
                  {d.rated_kw != null ? ` (≤${d.rated_kw} kW)` : ''}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-[#8b95a1]">
            Setpoint kW
            <input
              type="number"
              value={sp}
              onChange={(e) => setSp(e.target.value)}
              placeholder={chosen?.output_kw != null ? String(chosen.output_kw) : '0'}
              className="mt-1 block bg-[#0f1419] border border-[#232a33] rounded px-2 py-1 text-xs w-28"
            />
          </label>
          <button
            onClick={arm}
            disabled={sp === ''}
            className="text-xs px-3 py-1.5 rounded border border-[#f59e0b] text-[#fcd34d] hover:bg-[#1f1a0f] disabled:opacity-40"
          >
            ⚡ Arm dispatch
          </button>
          {chosen && (
            <span className="text-[11px] text-[#8b95a1]">
              now {chosen.output_kw != null ? `${chosen.output_kw} kW` : 'stale'} · a swing &gt; 10 kW is high-risk
            </span>
          )}
        </div>
      )}
    </div>
  );
}
