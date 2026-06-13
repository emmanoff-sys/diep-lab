'use client';

import { usePolling } from '@/lib/hooks';
import type { Asset, AssetHealthRow } from '@/lib/types';
import TwinCard from '@/components/TwinCard';
import { PageHeader } from '@/components/Section';
import { Loading, ErrorState } from '@/components/Loading';

export default function TwinsPage() {
  const assets = usePolling<{ assets: Asset[] }>('/assets', 8000);
  const health = usePolling<{ assets: AssetHealthRow[] }>('/health/assets', 8000);

  const healthById: Record<string, string> = {};
  (health.data?.assets || []).forEach((h) => (healthById[h.device_id] = h.health?.health));

  return (
    <div>
      <PageHeader title="Digital Twins" subtitle="Live virtual representation of every asset" />
      {assets.error ? (
        <ErrorState error={assets.error} />
      ) : assets.data ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {assets.data.assets.map((a) => (
            <TwinCard key={a.device_id} asset={a} health={healthById[a.device_id]} />
          ))}
        </div>
      ) : (
        <Loading />
      )}
    </div>
  );
}
