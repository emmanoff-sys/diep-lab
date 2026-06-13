// Ported from digitaltwin/app.py — per-device headline metrics and color maps.
// Keys are looked up first in live_state (canonical telemetry), then in
// asset_metadata (static spec), matching the original headline() behavior.

export const HEADLINE_METRICS: Record<string, [string, string][]> = {
  battery: [['SOC %', 'battery_soc'], ['Power kW', 'power_kw'], ['Capacity kWh', 'capacity_kwh']],
  solar_inverter: [['Solar kW', 'solar_kw'], ['Power kW', 'power_kw'], ['Capacity kW', 'capacity_kw']],
  ev_charger: [['Power kW', 'power_kw'], ['Voltage', 'voltage'], ['Max kW', 'max_power_kw']],
  microgrid: [['Frequency Hz', 'frequency'], ['Power kW', 'power_kw'], ['Solar kW', 'solar_kw']],
  smartmeter: [['Power kW', 'power_kw'], ['Voltage', 'voltage'], ['Solar kW', 'solar_kw'], ['Frequency Hz', 'frequency']],
};

export const HEALTH_COLORS: Record<string, string> = {
  OK: '#1f9d55',
  DEGRADED: '#d97706',
  OFFLINE: '#b91c1c',
  UNKNOWN: '#6b7280',
};

export const SEVERITY_COLORS: Record<string, string> = {
  HIGH: '#b91c1c',
  MEDIUM: '#d97706',
  LOW: '#2563eb',
  OK: '#1f9d55',
  INFO: '#6b7280',
};

export function headline(
  deviceType: string,
  state: Record<string, any> = {},
  meta: Record<string, any> = {},
): { label: string; value: any }[] {
  const out: { label: string; value: any }[] = [];
  for (const [label, key] of HEADLINE_METRICS[deviceType] || []) {
    const v = state?.[key] ?? meta?.[key];
    if (v === undefined || v === null) continue;
    out.push({ label, value: v });
  }
  return out;
}

export function fmt(value: any): string {
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(2);
  return String(value);
}
