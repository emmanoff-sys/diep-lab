'use client';

import dynamic from 'next/dynamic';
import { usePolling } from '@/lib/hooks';
import type { FleetOverview, Site, AssetHealthRow, Alarm, Recommendation } from '@/lib/types';
import MetricCard from '@/components/MetricCard';
import Section, { PageHeader } from '@/components/Section';
import AlarmTable from '@/components/AlarmTable';
import RecommendationList from '@/components/RecommendationList';
import { Loading } from '@/components/Loading';
import { GRAFANA_URL } from '@/lib/grafana';

const FleetMap = dynamic(() => import('@/components/FleetMap'), { ssr: false, loading: () => <Loading label="Loading map…" /> });

export default function DashboardPage() {
  const fleet = usePolling<FleetOverview>('/fleet/overview', 10000);
  const sites = usePolling<{ sites: Site[] }>('/sites/overview', 15000);
  const health = usePolling<{ assets: AssetHealthRow[] }>('/health/assets', 10000);
  const alarms = usePolling<{ alarms: Alarm[] }>('/alarms?limit=5', 10000);
  const recs = usePolling<{ recommendations: Recommendation[] }>('/recommendations', 30000);

  const total = fleet.data?.total_assets ?? 0;
  const healthRows = health.data?.assets ?? [];
  const online = healthRows.filter((h) => (h.health?.health || '').toUpperCase() === 'OK').length;
  const openAlarms = alarms.data?.alarms?.length ?? 0;
  const recCount = recs.data?.recommendations?.length ?? 0;

  return (
    <div>
      <PageHeader title="Dashboard" subtitle="Platform overview · live" />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <MetricCard label="Total assets" value={total} />
        <MetricCard label="Healthy (OK)" value={`${online}/${healthRows.length}`} />
        <MetricCard label="Open alarms" value={openAlarms} />
        <MetricCard label="Recommendations" value={recCount} />
      </div>

      <Section
        title="Fleet map"
        right={
          <a href={GRAFANA_URL} target="_blank" rel="noreferrer" className="text-xs text-[#5aa9e6]">
            ↗ Open Grafana for metrics
          </a>
        }
      >
        {sites.data ? <FleetMap sites={sites.data.sites} /> : <Loading label="Loading map…" />}
      </Section>

      <div className="grid md:grid-cols-2 gap-4">
        <Section title="Recent alarms">
          {alarms.data ? <AlarmTable alarms={alarms.data.alarms} /> : <Loading />}
        </Section>
        <Section title="Top recommendations">
          {recs.data ? <RecommendationList recs={recs.data.recommendations.slice(0, 5)} /> : <Loading />}
        </Section>
      </div>
    </div>
  );
}
