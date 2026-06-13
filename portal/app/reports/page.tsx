'use client';

import { usePolling } from '@/lib/hooks';
import type { ReportSummary } from '@/lib/types';
import MetricCard from '@/components/MetricCard';
import Section, { PageHeader } from '@/components/Section';
import { Loading } from '@/components/Loading';

function countMap(m: Record<string, number>) {
  const entries = Object.entries(m || {});
  if (!entries.length) return <div className="text-[#8b95a1] text-sm italic">None</div>;
  return (
    <table className="w-full text-sm">
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k} className="border-t border-[#232a33]">
            <td className="py-1.5 px-2 text-[#8b95a1]">{k}</td>
            <td className="py-1.5 px-2 text-right">{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function toCSV(s: ReportSummary): string {
  const lines: string[] = ['section,key,value'];
  s.device_summary.forEach((d) => lines.push(`devices,${d.device_type}/${d.status},${d.count}`));
  Object.entries(s.command_counts_by_status).forEach(([k, v]) => lines.push(`commands,${k},${v}`));
  Object.entries(s.derms_counts_by_status).forEach(([k, v]) => lines.push(`derms,${k},${v}`));
  Object.entries(s.alarm_counts_by_severity).forEach(([k, v]) => lines.push(`alarms,${k},${v}`));
  Object.entries(s.latest_telemetry).forEach(([k, v]) => lines.push(`latest_telemetry,${k},${v ?? ''}`));
  return lines.join('\n');
}

export default function ReportsPage() {
  const report = usePolling<ReportSummary>('/reports/summary', 30000);

  function exportCSV() {
    if (!report.data) return;
    const blob = new Blob([toCSV(report.data)], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'diep-report.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  const d = report.data;
  const totalDevices = d?.device_summary?.reduce((s, x) => s + x.count, 0) ?? 0;
  const totalCommands = d ? Object.values(d.command_counts_by_status).reduce((a, b) => a + b, 0) : 0;
  const totalAlarms = d ? Object.values(d.alarm_counts_by_severity).reduce((a, b) => a + b, 0) : 0;

  return (
    <div>
      <PageHeader title="Reports" subtitle="Operational rollups" />
      {!d ? (
        <Loading />
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            <MetricCard label="Devices" value={totalDevices} />
            <MetricCard label="Commands" value={totalCommands} />
            <MetricCard label="Alarms" value={totalAlarms} />
            <MetricCard label="Analytics events" value={d.analytics_event_count} />
          </div>

          <div className="mb-4">
            <button
              onClick={exportCSV}
              className="bg-[#232a33] hover:bg-[#2c333d] text-sm rounded px-4 py-1.5"
            >
              ⤓ Export CSV
            </button>
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            <Section title="Commands by status">{countMap(d.command_counts_by_status)}</Section>
            <Section title="DERMS by status">{countMap(d.derms_counts_by_status)}</Section>
            <Section title="Alarms by severity">{countMap(d.alarm_counts_by_severity)}</Section>
            <Section title="Latest telemetry">
              <table className="w-full text-sm">
                <tbody>
                  {Object.entries(d.latest_telemetry).map(([dev, t]) => (
                    <tr key={dev} className="border-t border-[#232a33]">
                      <td className="py-1.5 px-2 text-[#8b95a1]">{dev}</td>
                      <td className="py-1.5 px-2 text-right">{t ? new Date(t).toLocaleString() : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Section>
          </div>
        </>
      )}
    </div>
  );
}
