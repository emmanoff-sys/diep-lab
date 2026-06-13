'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { usePolling } from '@/lib/hooks';
import type { Asset, HealthVerdict, CommandRow, MaintenanceInsight } from '@/lib/types';
import { headline, fmt } from '@/lib/headlineMetrics';
import Section, { PageHeader } from '@/components/Section';
import StatusBadge from '@/components/StatusBadge';
import CommandModal from '@/components/CommandModal';
import { Loading, ErrorState } from '@/components/Loading';

function KVTable({ data }: { data: Record<string, any> }) {
  const entries = Object.entries(data || {});
  if (!entries.length) return <div className="text-[#8b95a1] text-sm italic">No data</div>;
  return (
    <table className="w-full text-sm">
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k} className="border-t border-[#232a33]">
            <td className="py-1.5 px-2 text-[#8b95a1]">{k}</td>
            <td className="py-1.5 px-2">{fmt(v)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function TwinDetailPage() {
  const { deviceId } = useParams<{ deviceId: string }>();
  const asset = usePolling<Asset>(`/assets/${deviceId}`, 6000);
  const health = usePolling<HealthVerdict>(`/assets/${deviceId}/health`, 8000);
  const commands = usePolling<{ commands: CommandRow[] }>(`/commands?device_id=${deviceId}&limit=10`, 8000);
  const maint = usePolling<MaintenanceInsight>(`/analytics/predictive_maintenance?device_id=${deviceId}`, 60000);
  const [showCmd, setShowCmd] = useState(false);

  if (asset.error) return <ErrorState error={asset.error} />;
  if (!asset.data) return <Loading />;

  const a = asset.data;
  const metrics = headline(a.device_type, a.current_state || {}, a.asset_metadata || {});

  return (
    <div>
      <div className="mb-4">
        <Link href="/twins" className="text-sm text-[#5aa9e6]">← all twins</Link>
      </div>
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-semibold">{a.device_id}</h1>
          <div className="text-sm text-[#8b95a1]">
            {a.device_type} · {a.site_name || '—'}
          </div>
        </div>
        <button
          onClick={() => setShowCmd(true)}
          className="bg-[#2563eb] hover:bg-[#1d4ed8] text-white text-sm rounded px-4 py-1.5"
        >
          Send command
        </button>
      </div>

      <Section title="Status" right={<StatusBadge label={health.data?.health} kind="health" />}>
        <div className="text-sm text-[#8b95a1] mb-3">{health.data?.reason || ''}</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {metrics.length ? (
            metrics.map((m) => (
              <div key={m.label} className="bg-[#0f1419] border border-[#232a33] rounded p-3">
                <div className="text-[#8b95a1] text-[11px]">{m.label}</div>
                <div className="text-lg font-semibold">{fmt(m.value)}</div>
              </div>
            ))
          ) : (
            <div className="text-[#8b95a1] text-sm italic">No live metrics yet</div>
          )}
        </div>
      </Section>

      <div className="grid md:grid-cols-2 gap-4">
        <Section title="Live state">
          <KVTable data={a.current_state || {}} />
        </Section>
        <Section title="Asset metadata">
          <KVTable data={a.asset_metadata || {}} />
        </Section>
      </div>

      <Section title="Recent commands">
        {commands.data?.commands?.length ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[#8b95a1] text-left">
                <th className="py-2 px-2">Command</th>
                <th className="py-2 px-2">Status</th>
                <th className="py-2 px-2">Created</th>
              </tr>
            </thead>
            <tbody>
              {commands.data.commands.map((c) => (
                <tr key={c.command_id} className="border-t border-[#232a33]">
                  <td className="py-2 px-2">{c.command_type}</td>
                  <td className="py-2 px-2"><StatusBadge label={c.status} /></td>
                  <td className="py-2 px-2 text-[#8b95a1]">{new Date(c.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="text-[#8b95a1] text-sm italic">No commands issued</div>
        )}
      </Section>

      {maint.data && (
        <Section title="Predictive maintenance" right={<StatusBadge label={maint.data.severity} kind="severity" />}>
          <div className="text-sm">Score: <b>{maint.data.score}</b></div>
          {maint.data.reasons?.length ? (
            <ul className="list-disc ml-5 mt-2 text-sm text-[#c2c9d1]">
              {maint.data.reasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          ) : (
            <div className="text-[#8b95a1] text-sm italic mt-2">No risk factors detected</div>
          )}
        </Section>
      )}

      {showCmd && <CommandModal deviceId={a.device_id} deviceType={a.device_type} onClose={() => setShowCmd(false)} />}
    </div>
  );
}
