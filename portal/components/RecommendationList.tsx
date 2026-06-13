'use client';

import type { Recommendation } from '@/lib/types';
import StatusBadge from './StatusBadge';

export default function RecommendationList({ recs }: { recs: Recommendation[] }) {
  if (!recs || recs.length === 0) {
    return <div className="text-[#8b95a1] text-sm italic py-3">No active recommendations.</div>;
  }
  return (
    <div className="flex flex-col gap-2">
      {recs.map((r, i) => (
        <div
          key={`${r.device_id}-${r.type}-${i}`}
          className="flex items-start justify-between gap-3 border border-[#232a33] rounded-lg p-3"
        >
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-sm">{r.device_id}</span>
              <StatusBadge label={r.severity} kind="severity" />
            </div>
            <div className="text-sm text-[#c2c9d1] mt-1">{r.message}</div>
            <div className="text-xs text-[#8b95a1] mt-1">→ {r.suggested_action}</div>
          </div>
          <code className="text-[11px] text-[#8b95a1] whitespace-nowrap">{r.suggested_endpoint}</code>
        </div>
      ))}
    </div>
  );
}
