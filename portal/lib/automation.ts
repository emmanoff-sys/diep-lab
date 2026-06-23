'use client';

// ADMS Phase 4 (P4-4) — client for the closed-loop automation engine.
// The portal exposes the governed automation surface: policy enable/mode toggles,
// the automation event feed, and the engine's posture. It never bypasses the
// governance — auto-execution is still gated server-side by OC_AUTOMATION_ENABLED
// + OC_CONTROLS_ENABLED + per-policy bounds.

import { usePolling } from './hooks';
import { postJSON } from './api';

export type PolicyMode = 'recommend' | 'auto';

export interface AutomationStatus {
  automation_enabled: boolean;
  controls_enabled: boolean;
  registered_kinds: string[];
  policies: number;
  enabled_policies: number;
  tripped_policies: string[];
  default_mode: PolicyMode;
  note: string;
}

export interface AutomationPolicy {
  policy_id: string;
  kind: string;
  description: string | null;
  enabled: boolean;
  mode: PolicyMode;
  params: Record<string, any>;
  bounds: Record<string, any>;
  consecutive_failures: number;
  tripped: boolean;
  last_run_at: string | null;
}

export type AutomationDecision =
  | 'proposed' | 'executed' | 'skipped' | 'blocked' | 'failed' | 'tripped' | 'config';

export interface AutomationEvent {
  event_id: number;
  policy_id: string;
  kind: string;
  decision: AutomationDecision;
  trigger: Record<string, any>;
  action_id: string | null;
  detail: Record<string, any>;
  at: string;
}

export function useAutomationStatus() {
  return usePolling<AutomationStatus>('/automation/status', 10000);
}
export function useAutomationPolicies() {
  return usePolling<{ policies: AutomationPolicy[] }>('/automation/policies', 8000);
}
export function useAutomationEvents(limit = 40) {
  return usePolling<{ events: AutomationEvent[] }>(`/automation/events?limit=${limit}`, 6000);
}

// PATCH isn't wrapped by lib/api (GET/POST/DELETE only); call the BFF directly.
export async function patchPolicy(
  policyId: string,
  body: { enabled?: boolean; mode?: PolicyMode; reset_trip?: boolean },
): Promise<AutomationPolicy> {
  const res = await fetch(`/api/diep/automation/policies/${policyId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`PATCH ${policyId} → ${res.status}: ${text}`);
  }
  return res.json();
}

// An action whose requested_by is "automation:<policy>" was created by the engine.
export const isAutomationActor = (requestedBy?: string | null) =>
  typeof requestedBy === 'string' && requestedBy.startsWith('automation:');
