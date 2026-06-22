'use client';

// ADMS Phase 2 (OC-5) — client for the governed operational-controls plane.
//
// Thin typed layer over the FastAPI `/controls/*` governance API (OC-1) plus the
// per-action handlers (OC-2 switch_op, OC-3 flisr, OC-4 voltvar_dispatch). The UI
// never actuates anything itself: it requests, approves, and executes governed
// actions and renders their state. Live actuation stays gated server-side by the
// OC_CONTROLS_ENABLED flag — this client surfaces that gate, it does not bypass it.

import { usePolling } from './hooks';
import { postJSON } from './api';

export type Risk = 'low' | 'high';
export type Mode = 'dry_run' | 'live';
export type ActionStatus =
  | 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXECUTED' | 'FAILED' | 'ROLLED_BACK';

export interface ControlStatus {
  controls_enabled: boolean;
  live_actuation: boolean;
  default_mode: string;
  registered_action_types: string[];
  approval: { high_risk: string; low_risk: string };
  request_roles: string[];
  approve_roles: string[];
}

export interface ControlAction {
  action_id: string;
  action_type: string;
  target: string | null;
  params: Record<string, any>;
  mode: Mode;
  risk: Risk;
  status: ActionStatus;
  reason: string | null;
  requested_by: string;
  approved_by: string | null;
  before_state: any;
  after_state: any;
  error: string | null;
  tenant_id: string | null;
  created_at: string;
  approved_at?: string | null;
  executed_at?: string | null;
  preview?: any;
}

export interface AuditEvent {
  event: string;
  actor: string;
  detail: any;
  at: string;
}

export interface Whoami {
  principal: string;
  role: string;
  tenant?: string | null;
}

// A draft is what a control surface (FLISR / Volt-VAR / switch list) hands to the
// console to be "armed" — the human intent, before any governed action exists.
export interface ControlDraft {
  action_type: 'flisr' | 'switch_op' | 'voltvar_dispatch' | string;
  target: string | null;
  params: Record<string, any>;
  summary: string;                              // one-line description shown on arm
  riskHint?: Risk;                              // best-effort; server is authoritative
  details?: { label: string; value: string }[];
}

// --- hooks -------------------------------------------------------------------
export function useWhoami() {
  return usePolling<Whoami>('/auth/whoami', 30000);
}
export function useControlStatus() {
  return usePolling<ControlStatus>('/controls/status', 15000);
}
export function useControlActions(limit = 25) {
  return usePolling<{ actions: ControlAction[] }>(`/controls/actions?limit=${limit}`, 5000);
}
export function useActionDetail(id: string | null) {
  return usePolling<ControlAction & { audit: AuditEvent[] }>(
    id ? `/controls/actions/${id}` : null,
    5000,
  );
}

// --- role gates (mirror FastAPI REQUEST_ROLES / APPROVE_ROLES) ---------------
const RANK: Record<string, number> = { viewer: 0, operator: 1, engineer: 2, admin: 3 };
export const canRequest = (role?: string) => (RANK[role ?? ''] ?? -1) >= RANK.operator;
export const canApprove = (role?: string) => (RANK[role ?? ''] ?? -1) >= RANK.engineer;

// Which governed transitions are offered for an action, given the viewer. The
// server is authoritative; these only decide what to *show* (and pre-explain).
export function affordances(a: ControlAction, role: string | undefined, me: string | undefined) {
  const req = canRequest(role);
  const app = canApprove(role);
  const isRequester = me != null && a.requested_by === me;
  const highSelf = a.risk === 'high' && isRequester;
  return {
    approve: app && a.status === 'PENDING' && !highSelf,
    reject: app && a.status === 'PENDING',
    execute:
      req &&
      ((a.mode === 'dry_run' && (a.status === 'PENDING' || a.status === 'APPROVED')) ||
        (a.mode === 'live' && a.status === 'APPROVED') ||
        (a.mode === 'live' && a.risk === 'low' && a.status === 'PENDING')),
    rollback: app && a.status === 'EXECUTED',
  };
}

// --- governed transitions ----------------------------------------------------
export const createAction = (d: ControlDraft, mode: Mode) =>
  postJSON<ControlAction>('/controls/actions', {
    action_type: d.action_type,
    target: d.target,
    params: d.params,
    mode,
    reason: d.summary,
  });
export const approveAction = (id: string, reason: string) =>
  postJSON<ControlAction>(`/controls/actions/${id}/approve`, { reason });
export const rejectAction = (id: string, reason: string) =>
  postJSON<ControlAction>(`/controls/actions/${id}/reject`, { reason });
export const executeAction = (id: string) =>
  postJSON<ControlAction>(`/controls/actions/${id}/execute`, {});
export const rollbackAction = (id: string) =>
  postJSON<ControlAction>(`/controls/actions/${id}/rollback`, {});
