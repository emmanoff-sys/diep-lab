'use client';

import { useState } from 'react';
import { usePolling } from '@/lib/hooks';
import type { Alarm } from '@/lib/types';
import AlarmTable from '@/components/AlarmTable';
import Section, { PageHeader } from '@/components/Section';
import { Loading } from '@/components/Loading';

export default function AlarmsPage() {
  const [device, setDevice] = useState('');
  const path = device ? `/alarms?device_id=${device}&limit=100` : '/alarms?limit=100';
  const alarms = usePolling<{ alarms: Alarm[] }>(path, 10000);

  return (
    <div>
      <PageHeader title="Alarms" subtitle="Device alarm log" />
      <Section
        title="Alarm log"
        right={
          <input
            placeholder="Filter device_id"
            value={device}
            onChange={(e) => setDevice(e.target.value.trim())}
            className="bg-[#0f1419] border border-[#232a33] rounded px-2 py-1 text-xs"
          />
        }
      >
        {alarms.data ? <AlarmTable alarms={alarms.data.alarms} /> : <Loading />}
      </Section>
    </div>
  );
}
