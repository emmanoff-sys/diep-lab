// TypeScript shapes mirroring the DIEP FastAPI responses, plus a client copy of
// the per-device command vocabulary used to constrain the command UI.

export interface Asset {
  device_id: string;
  device_type: string;
  location?: string | null;
  site_name?: string | null;
  site_type?: string | null;
  status: string;
  current_state?: Record<string, any>;
  asset_metadata?: Record<string, any>;
}

export interface HealthVerdict {
  health: string;
  reason?: string;
  [k: string]: any;
}

export interface AssetHealthRow {
  device_id: string;
  health: HealthVerdict;
}

export interface FleetOverview {
  total_assets: number;
  by_device_type: Record<string, Record<string, number>>;
  by_site: Record<string, number>;
}

export interface Site {
  site_name: string;
  site_type: string;
  latitude: number | null;
  longitude: number | null;
  asset_count: number;
  online_assets: number;
  latest_telemetry: string | null;
}

export interface CommandRow {
  command_id: string;
  device_id: string;
  command_type: string;
  status: string;
  created_at: string;
}

export interface DermsRequest {
  request_id: string;
  request_type: string;
  site_name?: string | null;
  device_id?: string | null;
  params: any;
  status: string;
  created_at: string;
  executed_at?: string | null;
  completed_at?: string | null;
  error_message?: string | null;
}

export interface ForecastPoint {
  time: string;
  power_kw?: number;
  solar_kw?: number;
  battery_soc?: number;
}

export interface Anomaly {
  time: string;
  metric: string;
  value: number;
  threshold_high?: number;
  threshold_low?: number;
  reason: string;
}

export interface MaintenanceInsight {
  device_id: string;
  device_type: string;
  status: string;
  severity: string;
  score: number;
  reasons: string[];
}

export interface Recommendation {
  device_id: string;
  type: string;
  severity: string;
  message: string;
  suggested_action: string;
  suggested_endpoint: string;
}

export interface Alarm {
  id: number;
  device_id: string;
  alarm_type?: string;
  severity?: string;
  message?: string;
  metadata?: any;
  raised_at?: string;
}

export interface ReportSummary {
  site_name: string | null;
  device_summary: { device_type: string; status: string; count: number }[];
  analytics_event_count: number;
  command_counts_by_status: Record<string, number>;
  derms_counts_by_status: Record<string, number>;
  alarm_counts_by_severity: Record<string, number>;
  latest_telemetry: Record<string, string | null>;
  note?: string;
}

// Mirrors ALLOWED_COMMANDS in fastapi/app.py. Used to constrain CommandModal.
export const ALLOWED_COMMANDS: Record<string, string[]> = {
  ev_charger: ['start_charging', 'stop_charging', 'set_limit'],
  battery: ['charge', 'discharge', 'set_soc_target', 'idle'],
  solar_inverter: ['curtail', 'set_limit', 'resume'],
  microgrid: ['island', 'grid_connect', 'set_setpoint'],
};
