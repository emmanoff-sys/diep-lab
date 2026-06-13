'use client';

import Link from 'next/link';
import type { Asset } from '@/lib/types';
import { headline, fmt } from '@/lib/headlineMetrics';
import StatusBadge from './StatusBadge';

export default function TwinCard({ asset, health }: { asset: Asset; health?: string }) {
  const metrics = headline(asset.device_type, asset.current_state || {}, asset.asset_metadata || {});
  const lastCmd = asset.current_state?.last_command_type;
  const lastCmdStatus = asset.current_state?.last_command_status;
  return (
    <Link
      href={`/twins/${asset.device_id}`}
      className="block bg-[#161b22] border border-[#232a33] rounded-lg p-4 hover:border-[#3b82f6] transition-colors"
    >
      <div className="flex items-center justify-between">
        <span className="text-base font-semibold">{asset.device_id}</span>
        <StatusBadge label={health} kind="health" />
      </div>
      <div className="text-[#8b95a1] text-xs uppercase tracking-wide">{asset.device_type}</div>
      <div className="text-[#8b95a1] text-xs mb-3">{asset.site_name || asset.location || '—'}</div>
      <div className="grid grid-cols-2 gap-y-2 gap-x-3">
        {metrics.length ? (
          metrics.map((m) => (
            <div key={m.label}>
              <div className="text-[#8b95a1] text-[11px]">{m.label}</div>
              <div className="text-sm font-semibold">{fmt(m.value)}</div>
            </div>
          ))
        ) : (
          <div className="text-[#8b95a1] text-xs italic">No live metrics yet</div>
        )}
      </div>
      <div className="mt-3 pt-2 border-t border-[#232a33] text-xs text-[#8b95a1]">
        {lastCmd ? (
          <>
            Last: <b className="text-[#c2c9d1]">{lastCmd}</b> · {lastCmdStatus}
          </>
        ) : (
          'No commands issued'
        )}
      </div>
    </Link>
  );
}
