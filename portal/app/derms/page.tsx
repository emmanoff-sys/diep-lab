'use client';

import { usePolling } from '@/lib/hooks';
import type { DermsRequest } from '@/lib/types';
import DermsActionPanel from '@/components/DermsActionPanel';
import Section, { PageHeader } from '@/components/Section';
import StatusBadge from '@/components/StatusBadge';
import { Loading } from '@/components/Loading';

export default function DermsPage() {
  const requests = usePolling<{ requests: DermsRequest[] }>('/derms/requests?limit=50', 5000);

  return (
    <div>
      <PageHeader title="DERMS" subtitle="Distributed energy resource management — grid services" />
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
