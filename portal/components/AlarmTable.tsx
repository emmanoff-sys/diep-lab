'use client';

import type { Alarm } from '@/lib/types';
import StatusBadge from './StatusBadge';

export default function AlarmTable({ alarms }: { alarms: Alarm[] }) {
  if (!alarms || alarms.length === 0) {
    return <div className="text-[#8b95a1] text-sm italic py-3">No alarms.</div>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-[#8b95a1] text-left">
            <th className="py-2 px-2">Raised</th>
            <th className="py-2 px-2">Device</th>
            <th className="py-2 px-2">Type</th>
            <th className="py-2 px-2">Severity</th>
            <th className="py-2 px-2">Message</th>
          </tr>
        </thead>
        <tbody>
          {alarms.map((a) => (
            <tr key={a.id} className="border-t border-[#232a33]">
              <td className="py-2 px-2 text-[#8b95a1]">
                {a.raised_at ? new Date(a.raised_at).toLocaleString() : '—'}
              </td>
              <td className="py-2 px-2">{a.device_id}</td>
              <td className="py-2 px-2 text-[#c2c9d1]">{a.alarm_type || '—'}</td>
              <td className="py-2 px-2">
                <StatusBadge label={a.severity} kind="severity" />
              </td>
              <td className="py-2 px-2 text-[#c2c9d1]">{a.message || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
