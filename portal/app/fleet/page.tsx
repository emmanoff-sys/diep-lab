'use client';

import { useState } from 'react';
import dynamic from 'next/dynamic';
import { usePolling } from '@/lib/hooks';
import type { Asset, AssetHealthRow, Site } from '@/lib/types';
import AssetTable from '@/components/AssetTable';
import CommandModal from '@/components/CommandModal';
import Section, { PageHeader } from '@/components/Section';
import { Loading, ErrorState } from '@/components/Loading';

const FleetMap = dynamic(() => import('@/components/FleetMap'), { ssr: false, loading: () => <Loading label="Loading map…" /> });

export default function FleetPage() {
  const assets = usePolling<{ assets: Asset[] }>('/assets', 8000);
  const health = usePolling<{ assets: AssetHealthRow[] }>('/health/assets', 8000);
  const sites = usePolling<{ sites: Site[] }>('/sites/overview', 15000);
  const [target, setTarget] = useState<Asset | null>(null);
  const [typeFilter, setTypeFilter] = useState('');

  const healthById: Record<string, string> = {};
  (health.data?.assets || []).forEach((h) => (healthById[h.device_id] = h.health?.health));

  let rows = assets.data?.assets || [];
  if (typeFilter) rows = rows.filter((a) => a.device_type === typeFilter);
  const types = Array.from(new Set((assets.data?.assets || []).map((a) => a.device_type)));

  return (
    <div>
      <PageHeader title="Fleet Management" subtitle="Assets, locations, and control" />

      <Section title="Site map">
        {sites.data ? <FleetMap sites={sites.data.sites} height={340} /> : <Loading label="Loading map…" />}
      </Section>

      <Section
        title="Assets"
        right={
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="bg-[#0f1419] border border-[#232a33] rounded px-2 py-1 text-xs"
          >
            <option value="">All types</option>
            {types.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        }
      >
        {assets.error ? (
          <ErrorState error={assets.error} />
        ) : assets.data ? (
          <AssetTable assets={rows} healthById={healthById} onCommand={setTarget} />
        ) : (
          <Loading />
        )}
      </Section>

      {target && (
        <CommandModal deviceId={target.device_id} deviceType={target.device_type} onClose={() => setTarget(null)} />
      )}
    </div>
  );
}
