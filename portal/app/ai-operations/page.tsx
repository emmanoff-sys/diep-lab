'use client';

import { useState } from 'react';
import { usePolling } from '@/lib/hooks';
import type { Asset, Recommendation, ForecastPoint, Anomaly, MaintenanceInsight } from '@/lib/types';
import Section, { PageHeader } from '@/components/Section';
import RecommendationList from '@/components/RecommendationList';
import TimeSeriesChart from '@/components/TimeSeriesChart';
import StatusBadge from '@/components/StatusBadge';
import { Loading } from '@/components/Loading';

export default function AiOperationsPage() {
  const assets = usePolling<{ assets: Asset[] }>('/assets', 30000);
  const [device, setDevice] = useState('BAT001');

  const recs = usePolling<{ recommendations: Recommendation[] }>('/recommendations', 30000);
  const forecast = usePolling<{ forecast: ForecastPoint[] }>(`/analytics/forecast?device_id=${device}&horizon_hours=12`, 60000);
  const anomalies = usePolling<{ anomalies: Anomaly[] }>(`/analytics/anomalies?device_id=${device}`, 30000);
  const maint = usePolling<MaintenanceInsight>(`/analytics/predictive_maintenance?device_id=${device}`, 60000);

  return (
    <div>
      <PageHeader title="AI Operations" subtitle="Forecasts, anomalies, predictive maintenance, recommendations" />

      <Section title="Recommendations (fleet)">
        {recs.data ? <RecommendationList recs={recs.data.recommendations} /> : <Loading />}
      </Section>

      <Section
        title="Analytics"
        right={
          <select
            value={device}
            onChange={(e) => setDevice(e.target.value)}
            className="bg-[#0f1419] border border-[#232a33] rounded px-2 py-1 text-xs"
          >
            {(assets.data?.assets || [{ device_id: 'BAT001' } as Asset]).map((a) => (
              <option key={a.device_id} value={a.device_id}>{a.device_id}</option>
            ))}
          </select>
        }
      >
        <div className="mb-2 text-xs text-[#8b95a1]">Forecast (12h)</div>
        {forecast.data?.forecast?.length ? (
          <TimeSeriesChart
            data={forecast.data.forecast}
            series={[
              { key: 'power_kw', color: '#3b82f6', name: 'Power kW' },
              { key: 'solar_kw', color: '#f59e0b', name: 'Solar kW' },
              { key: 'battery_soc', color: '#10b981', name: 'SOC %' },
            ]}
          />
        ) : (
          <div className="text-[#8b95a1] text-sm italic">No forecast data.</div>
        )}
      </Section>

      <div className="grid md:grid-cols-2 gap-4">
        <Section
          title="Predictive maintenance"
          right={maint.data ? <StatusBadge label={maint.data.severity} kind="severity" /> : null}
        >
          {maint.data ? (
            <>
              <div className="text-sm">Score: <b>{maint.data.score}</b></div>
              {maint.data.reasons?.length ? (
                <ul className="list-disc ml-5 mt-2 text-sm text-[#c2c9d1]">
                  {maint.data.reasons.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
              ) : (
                <div className="text-[#8b95a1] text-sm italic mt-2">No risk factors.</div>
              )}
            </>
          ) : (
            <Loading />
          )}
        </Section>

        <Section title="Anomalies">
          {anomalies.data ? (
            anomalies.data.anomalies.length ? (
              <div className="overflow-x-auto max-h-72 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-[#8b95a1] text-left">
                      <th className="py-2 px-2">Time</th>
                      <th className="py-2 px-2">Metric</th>
                      <th className="py-2 px-2">Value</th>
                      <th className="py-2 px-2">Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {anomalies.data.anomalies.slice(0, 50).map((an, i) => (
                      <tr key={i} className="border-t border-[#232a33]">
                        <td className="py-1.5 px-2 text-[#8b95a1]">{new Date(an.time).toLocaleTimeString()}</td>
                        <td className="py-1.5 px-2">{an.metric}</td>
                        <td className="py-1.5 px-2">{an.value}</td>
                        <td className="py-1.5 px-2 text-[#c2c9d1]">{an.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-[#8b95a1] text-sm italic">No anomalies detected.</div>
            )
          ) : (
            <Loading />
          )}
        </Section>
      </div>
    </div>
  );
}
