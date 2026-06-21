'use client';

import { usePolling } from '@/lib/hooks';
import type { DermsRequest } from '@/lib/types';
import DermsActionPanel from '@/components/DermsActionPanel';
import Section, { PageHeader } from '@/components/Section';
import StatusBadge from '@/components/StatusBadge';
import MetricCard from '@/components/MetricCard';
import { Loading } from '@/components/Loading';

interface DerAsset {
  der_id: string;
  der_type: string;
  node_id: string | null;
  rated_kw: number | null;
  rated_kwh: number | null;
  vpp_group: string | null;
  output_kw: number | null;
  online: boolean;
}
interface Fleet {
  der_count: number;
  online: number;
  total_rated_kw: number;
  total_storage_kwh: number;
  total_output_kw: number;
}

export default function DermsPage() {
  const requests = usePolling<{ requests: DermsRequest[] }>('/derms/requests?limit=50', 5000);
  const fleet = usePolling<Fleet>('/der/fleet', 8000);
  const assets = usePolling<{ der_assets: DerAsset[] }>('/der/assets', 8000);

  return (
    <div>
      <PageHeader title="DERMS" subtitle="Distributed energy resource management — registry, aggregation, grid services" />

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
        <MetricCard label="DER assets" value={fleet.data ? fleet.data.der_count : '—'} />
        <MetricCard label="Online" value={fleet.data ? fleet.data.online : '—'} />
        <MetricCard label="Rated capacity" value={fleet.data ? `${fleet.data.total_rated_kw} kW` : '—'} />
        <MetricCard label="Storage" value={fleet.data ? `${fleet.data.total_storage_kwh} kWh` : '—'} />
        <MetricCard label="Live output" value={fleet.data ? `${fleet.data.total_output_kw} kW` : '—'} />
      </div>

      <Section title="DER registry" right={<span className="text-xs text-[#8b95a1]">bound to grid nodes</span>}>
        {assets.data ? (
          <table className="w-full text-sm">
            <thead className="text-[#8b95a1] text-xs text-left">
              <tr>
                <th className="py-1 px-2">DER</th><th className="px-2">Type</th><th className="px-2">Node</th>
                <th className="px-2">Rated kW</th><th className="px-2">Storage kWh</th>
                <th className="px-2">Output kW</th><th className="px-2">VPP</th><th className="px-2">State</th>
              </tr>
            </thead>
            <tbody>
              {assets.data.der_assets.map((a) => (
                <tr key={a.der_id} className="border-t border-[#232a33]">
                  <td className="py-1.5 px-2 font-mono text-xs">{a.der_id}</td>
                  <td className="px-2 text-xs">{a.der_type}</td>
                  <td className="px-2 text-xs text-[#8b95a1]">{a.node_id}</td>
                  <td className="px-2">{a.rated_kw ?? '—'}</td>
                  <td className="px-2">{a.rated_kwh ?? '—'}</td>
                  <td className="px-2">{a.output_kw ?? '—'}</td>
                  <td className="px-2 text-xs">{a.vpp_group}</td>
                  <td className="px-2"><StatusBadge label={a.online ? 'ONLINE' : 'OFFLINE'} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Loading />
        )}
      </Section>

      <div className="grid lg:grid-cols-2 gap-4">
        <Section title="New request">
          <DermsActionPanel onSubmitted={() => requests.mutate()} />
        </Section>
        <Section title="Request log" right={<span className="text-xs text-[#8b95a1]">polls 5s</span>}>
          {requests.data ? (
            requests.data.requests.length ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-[#8b95a1] text-left">
                      <th className="py-2 px-2">Type</th>
                      <th className="py-2 px-2">Device</th>
                      <th className="py-2 px-2">Status</th>
                      <th className="py-2 px-2">Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    {requests.data.requests.map((r) => (
                      <tr key={r.request_id} className="border-t border-[#232a33]">
                        <td className="py-2 px-2">{r.request_type}</td>
                        <td className="py-2 px-2 text-[#c2c9d1]">{r.device_id || r.site_name || '—'}</td>
                        <td className="py-2 px-2"><StatusBadge label={r.status} /></td>
                        <td className="py-2 px-2 text-[#8b95a1]">{new Date(r.created_at).toLocaleTimeString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-[#8b95a1] text-sm italic">No DERMS requests yet.</div>
            )
          ) : (
            <Loading />
          )}
        </Section>
      </div>
    </div>
  );
}
