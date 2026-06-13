'use client';

import Link from 'next/link';
import type { Asset, AssetHealthRow } from '@/lib/types';
import { headline, fmt } from '@/lib/headlineMetrics';
import StatusBadge from './StatusBadge';

export default function AssetTable({
  assets,
  healthById,
  onCommand,
}: {
  assets: Asset[];
  healthById?: Record<string, string>;
  onCommand?: (a: Asset) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-[#8b95a1] text-left">
            <th className="py-2 px-2">Device</th>
            <th className="py-2 px-2">Type</th>
            <th className="py-2 px-2">Site</th>
            <th className="py-2 px-2">Status</th>
            <th className="py-2 px-2">Health</th>
            <th className="py-2 px-2">Headline</th>
            {onCommand && <th className="py-2 px-2">Action</th>}
          </tr>
        </thead>
        <tbody>
          {assets.map((a) => {
            const metrics = headline(a.device_type, a.current_state || {}, a.asset_metadata || {});
            return (
              <tr key={a.device_id} className="border-t border-[#232a33]">
                <td className="py-2 px-2">
                  <Link href={`/twins/${a.device_id}`} className="text-[#5aa9e6] hover:underline">
                    {a.device_id}
                  </Link>
                </td>
                <td className="py-2 px-2 text-[#c2c9d1]">{a.device_type}</td>
                <td className="py-2 px-2 text-[#8b95a1]">{a.site_name || '—'}</td>
                <td className="py-2 px-2">
                  <StatusBadge label={a.status} />
                </td>
                <td className="py-2 px-2">
                  <StatusBadge label={healthById?.[a.device_id]} kind="health" />
                </td>
                <td className="py-2 px-2 text-[#c2c9d1]">
                  {metrics.slice(0, 2).map((m) => `${m.label}: ${fmt(m.value)}`).join('  ·  ') || '—'}
                </td>
                {onCommand && (
                  <td className="py-2 px-2">
                    <button
                      onClick={() => onCommand(a)}
                      className="bg-[#232a33] hover:bg-[#2c333d] text-xs rounded px-2 py-1"
                    >
                      Command
                    </button>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
