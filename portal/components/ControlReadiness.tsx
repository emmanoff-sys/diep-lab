'use client';

import { useReadiness, auditExportHref } from '@/lib/controls';

// OC-6 — control-readiness & safety reporting panel. Reads
// GET /controls/report/readiness and renders the safety posture, queue state,
// 24h activity, and any readiness warnings, plus a one-click audit CSV export.
// Read-only: it reports on the control plane, it does not actuate.

function Stat({ label, value, accent }: { label: string; value: number | string; accent?: string }) {
  return (
    <div className="bg-[#0f1419] border border-[#232a33] rounded px-2 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-[#8b95a1]">{label}</div>
      <div className="text-base font-semibold" style={{ color: accent ?? '#c2c9d1' }}>{value}</div>
    </div>
  );
}

export default function ControlReadiness() {
  const r = useReadiness();
  const d = r.data;
  const a = d?.activity_24h;
  const oldestMin = d?.oldest_pending_age_seconds != null ? Math.round(d.oldest_pending_age_seconds / 60) : null;

  return (
    <div className="border border-[#232a33] rounded-lg p-3 bg-[#11161c] space-y-3 text-sm">
      <div className="flex items-center justify-between">
        <div className="text-[11px] uppercase tracking-wider text-[#8b95a1]">Control readiness &amp; safety</div>
        <div className="flex items-center gap-2">
          {d && (
            <span
              className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded border ${
                d.ready ? 'border-[#22c55e] text-[#86efac]' : 'border-[#ef4444] text-[#fca5a5]'
              }`}
            >
              {d.ready ? 'ready' : 'attention'}
            </span>
          )}
          <a
            href={auditExportHref(720)}
            className="text-[11px] px-2 py-0.5 rounded border border-[#3b82f6] text-[#93c5fd] hover:bg-[#11203a]"
            title="Download the governed audit trail (last 30 days) as CSV"
          >
            ↓ Export audit (CSV)
          </a>
        </div>
      </div>

      {!d ? (
        <div className="text-xs text-[#8b95a1]">Loading readiness…</div>
      ) : (
        <>
          {/* Queue state */}
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
            <Stat label="Pending" value={d.counts.PENDING ?? 0} accent={(d.counts.PENDING ?? 0) ? '#fcd34d' : '#8b95a1'} />
            <Stat label="Awaiting approval" value={d.awaiting_approval} accent={d.awaiting_approval ? '#fcd34d' : '#8b95a1'} />
            <Stat label="Approved" value={d.counts.APPROVED ?? 0} accent="#93c5fd" />
            <Stat label="Executed" value={d.counts.EXECUTED ?? 0} accent="#86efac" />
            <Stat label="Failed" value={d.counts.FAILED ?? 0} accent={(d.counts.FAILED ?? 0) ? '#fca5a5' : '#8b95a1'} />
            <Stat label="Rolled back" value={d.counts.ROLLED_BACK ?? 0} accent="#9ca3af" />
          </div>

          {/* 24h activity */}
          {a && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-[#8b95a1] mb-1">Last 24 hours</div>
              <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
                <Stat label="Requested" value={a.requested} />
                <Stat label="Dry-runs" value={a.dry_runs} />
                <Stat label="Live executed" value={a.executed_live} accent={a.executed_live ? '#fca5a5' : '#8b95a1'} />
                <Stat label="Blocked" value={a.blocked} accent={a.blocked ? '#fcd34d' : '#8b95a1'} />
                <Stat label="Failed" value={a.failed} accent={a.failed ? '#fca5a5' : '#8b95a1'} />
                <Stat label="Rolled back" value={a.rolled_back} accent="#9ca3af" />
              </div>
            </div>
          )}

          {oldestMin != null && (
            <div className="text-[11px] text-[#8b95a1]">
              Oldest pending action: <span className="font-mono text-[#c2c9d1]">{oldestMin} min</span>
            </div>
          )}

          {/* Readiness warnings */}
          {d.warnings.length > 0 ? (
            <ul className="space-y-1">
              {d.warnings.map((w, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-[#fcd34d]">
                  <span className="text-[#a16207]">▲</span>
                  <span>{w}</span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-xs text-[#86efac]">No readiness warnings — control plane nominal.</div>
          )}
        </>
      )}
    </div>
  );
}
