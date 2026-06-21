'use client';

import { useState } from 'react';
import { usePolling } from '@/lib/hooks';
import Section, { PageHeader } from '@/components/Section';
import MetricCard from '@/components/MetricCard';
import TimeSeriesChart from '@/components/TimeSeriesChart';
import { Loading } from '@/components/Loading';
import type { Asset } from '@/lib/types';

interface ForecastResp {
  device_id: string;
  method: string;
  history_points: number;
  history_span_hours: number;
  recent_moving_avg_kw: number;
  forecast: { time: string; forecast_kw: number }[];
}

export default function ForecastingPage() {
  const [device, setDevice] = useState('BAT001');
  const [horizon, setHorizon] = useState(24);
  const assets = usePolling<{ assets: Asset[] }>('/assets', 30000);
  const fc = usePolling<ForecastResp>(
    device ? `/forecast/load?device_id=${device}&horizon_hours=${horizon}` : null, 15000);

  // TimeSeriesChart expects [{time, <series>}]; map forecast_kw -> power_kw.
  const series = (fc.data?.forecast || []).map((p) => ({ time: p.time, power_kw: p.forecast_kw }));

  return (
    <div>
      <PageHeader title="Load Forecasting" subtitle="Short-term load forecast (moving-average + daily seasonal)" />

      <Section
        title="Forecast"
        right={
          <div className="flex gap-2 items-center text-xs">
            <select
              value={device}
              onChange={(e) => setDevice(e.target.value)}
              className="bg-[#0f1419] border border-[#232a33] rounded px-2 py-1"
            >
              {(assets.data?.assets || []).map((a) => (
                <option key={a.device_id} value={a.device_id}>{a.device_id}</option>
              ))}
            </select>
            <select
              value={horizon}
              onChange={(e) => setHorizon(Number(e.target.value))}
              className="bg-[#0f1419] border border-[#232a33] rounded px-2 py-1"
            >
              <option value={12}>12h</option>
              <option value={24}>24h</option>
              <option value={48}>48h</option>
            </select>
          </div>
        }
      >
        {fc.data ? (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              <MetricCard label="Method" value={<span className="text-sm">{fc.data.method}</span>} />
              <MetricCard label="History points" value={fc.data.history_points} />
              <MetricCard label="History span" value={`${fc.data.history_span_hours} h`} />
              <MetricCard label="Recent avg" value={`${fc.data.recent_moving_avg_kw} kW`} />
            </div>
            {series.length ? (
              <TimeSeriesChart data={series} series={[{ key: 'power_kw', color: '#5aa9e6', name: 'Forecast kW' }]} />
            ) : (
              <div className="text-[#8b95a1] text-sm italic">No forecast points.</div>
            )}
          </>
        ) : fc.error ? (
          <div className="text-[#f87171] text-sm">No telemetry history for {device} yet.</div>
        ) : (
          <Loading />
        )}
      </Section>
    </div>
  );
}
