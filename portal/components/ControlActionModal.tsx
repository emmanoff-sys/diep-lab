'use client';

import { useState } from 'react';
import type { ControlDraft, ControlAction, Mode } from '@/lib/controls';
import { createAction } from '@/lib/controls';

// OC-5 — the "arm" confirmation modal. A control surface hands us a ControlDraft
// (the human intent); here the operator chooses dry-run vs live and confirms,
// which *requests* a governed action (POST /controls/actions). It actuates
// nothing — request is always separate from execute, and live execution still
// needs approval + the master flag, which happens later in the action queue.

export default function ControlActionModal({
  draft,
  liveEnabled,
  onClose,
  onCreated,
}: {
  draft: ControlDraft;
  liveEnabled: boolean; // OC_CONTROLS_ENABLED — affects messaging only, never the gate
  onClose: () => void;
  onCreated: (a: ControlAction) => void;
}) {
  const [mode, setMode] = useState<Mode>('dry_run');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const high = draft.riskHint === 'high';
  const live = mode === 'live';

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      const a = await createAction(draft, mode);
      onCreated(a);
    } catch (e: any) {
      const msg = String(e?.message || e);
      if (msg.includes('403')) setError('Your role cannot request control actions (operator+ required).');
      else if (msg.includes('409')) setError(`Blocked by a safety interlock: ${msg.split(':').slice(1).join(':').trim() || 'see details'}`);
      else if (msg.includes('404')) setError('Target not found in the network model.');
      else setError(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className={`bg-[#161b22] border rounded-lg p-5 w-[460px] max-w-[92vw] ${
          live ? 'border-[#ef4444]' : 'border-[#232a33]'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-white">Arm control action</h3>
          <button onClick={onClose} className="text-[#8b95a1] hover:text-white">✕</button>
        </div>

        {/* Intent */}
        <div className="text-sm text-[#c2c9d1] mb-2">{draft.summary}</div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="font-mono text-[11px] px-2 py-0.5 rounded border border-[#232a33] text-[#8b95a1]">
            {draft.action_type}
          </span>
          {draft.target && (
            <span className="font-mono text-[11px] px-2 py-0.5 rounded border border-[#232a33] text-[#8b95a1]">
              {draft.target}
            </span>
          )}
          <span
            className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded border ${
              high ? 'border-[#ef4444] text-[#fca5a5]' : 'border-[#22c55e] text-[#86efac]'
            }`}
          >
            {high ? 'high risk · two-person' : 'low risk · single operator'}
          </span>
        </div>

        {/* Plan-relevant details (best-effort; the server re-plans authoritatively) */}
        {draft.details && draft.details.length > 0 && (
          <div className="grid grid-cols-2 gap-1.5 mb-3">
            {draft.details.map((d) => (
              <div key={d.label} className="bg-[#0f1419] border border-[#232a33] rounded px-2 py-1">
                <div className="text-[10px] uppercase tracking-wider text-[#8b95a1]">{d.label}</div>
                <div className="text-xs text-[#c2c9d1] font-mono">{d.value}</div>
              </div>
            ))}
          </div>
        )}

        {/* Mode selector */}
        <div className="text-[11px] uppercase tracking-wider text-[#8b95a1] mb-1">Mode</div>
        <div className="grid grid-cols-2 gap-2 mb-3">
          <button
            onClick={() => setMode('dry_run')}
            className={`text-xs px-3 py-2 rounded border text-left ${
              !live ? 'border-[#3b82f6] bg-[#11161c] text-white' : 'border-[#232a33] text-[#8b95a1]'
            }`}
          >
            <div className="font-semibold">Dry-run</div>
            <div className="text-[10px] text-[#8b95a1]">Plan + audit only · no actuation</div>
          </button>
          <button
            onClick={() => setMode('live')}
            className={`text-xs px-3 py-2 rounded border text-left ${
              live ? 'border-[#ef4444] bg-[#1a1113] text-white' : 'border-[#232a33] text-[#8b95a1]'
            }`}
          >
            <div className="font-semibold">Live</div>
            <div className="text-[10px] text-[#8b95a1]">Real actuation · governed</div>
          </button>
        </div>

        {/* Governance explainer */}
        <div className="text-[11px] text-[#8b95a1] bg-[#0f1419] border border-[#232a33] rounded px-2 py-1.5 mb-3">
          {!live ? (
            <>This requests a <span className="text-[#86efac]">dry-run</span>: it records the plan and an audit
            entry but operates nothing. Safe to arm at any time.</>
          ) : high ? (
            <>This arms a <span className="text-[#fca5a5]">live, high-risk</span> action. It must be approved by a
            different user (two-person rule), then executed. {liveEnabled
              ? 'Operational controls are ENABLED — execution will actuate.'
              : 'Operational controls are currently DISABLED, so execution will be refused until the master flag is on.'}</>
          ) : (
            <>This arms a <span className="text-[#fca5a5]">live, low-risk</span> action — a single operator may
            execute it (no separate approver). {liveEnabled
              ? 'Operational controls are ENABLED — execution will actuate.'
              : 'Operational controls are currently DISABLED, so execution will be refused until the master flag is on.'}</>
          )}
        </div>

        {error && <div className="text-xs text-[#fca5a5] mb-2">{error}</div>}

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="text-xs px-3 py-1.5 rounded border border-[#232a33] text-[#8b95a1] hover:bg-[#11161c]">
            Cancel
          </button>
          <button
            onClick={confirm}
            disabled={busy}
            className={`text-xs px-3 py-1.5 rounded text-white disabled:opacity-50 ${
              live ? 'bg-[#dc2626] hover:bg-[#b91c1c]' : 'bg-[#2563eb] hover:bg-[#1d4ed8]'
            }`}
          >
            {busy ? 'Arming…' : live ? 'Arm LIVE action' : 'Arm dry-run'}
          </button>
        </div>
      </div>
    </div>
  );
}
