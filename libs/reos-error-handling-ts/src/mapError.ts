/**
 * mapErrorToUiState — DAEP / RE-OS shared error mapping (Next.js).
 *
 * Authority: WP-002-06 | DRDP v1.0 §21.3 (Standard Error Code Handling —
 * status-to-behavior table), §22 (Error state: no blank screens, ever).
 * Consumes the RFC 7807 shape produced by libs/reos-exceptions (WP-002-05).
 *
 * Security (WP-002-06 §25): the 500 state surfaces ONLY the `error_id`
 * reference — every field outside the approved shape is stripped; raw stack
 * traces or internal messages never reach the UI.
 */

import { log } from "@reos/logging";

import { USER_MESSAGES } from "./messages";

/** RFC 7807 Problem Details response (WP-002-05 contract). */
export interface Rfc7807Response {
  type?: string;
  title?: string;
  status: number;
  detail?: string;
  instance?: string;
  code?: string;
  /** RFC 7807 extension members (metadata from the backend). */
  [extension: string]: unknown;
}

/** Discriminated UI error states per DRDP v1.0 §21.3. */
export type ErrorUiState =
  | {
      kind: "form_validation"; // 400 / 422 — inline field errors
      userMessage: string;
      fieldErrors: Record<string, string>;
    }
  | {
      kind: "redirect_sign_in"; // 401 — preserve route, toast
      userMessage: string;
      preserveCurrentRoute: true;
    }
  | {
      kind: "permission_denied"; // 403 — descriptor, never blank
      userMessage: string;
    }
  | {
      kind: "not_found"; // 404 — illustration + breadcrumb-preserved nav
      userMessage: string;
      showIllustration: true;
      preserveBreadcrumbs: true;
    }
  | {
      kind: "conflict"; // 409 — context-specific message
      userMessage: string;
      contextDetail: string;
    }
  | {
      kind: "rate_limited"; // 429 — countdown timer
      userMessage: string;
      retryAfterSeconds: number;
    }
  | {
      kind: "server_error"; // 500 — generic + error_id for support
      userMessage: string;
      errorId: string | null;
    }
  | {
      kind: "maintenance"; // 503 — maintenance / degradation
      userMessage: string;
    };

const DEFAULT_RETRY_AFTER_SECONDS = 30;

function extractFieldErrors(response: Rfc7807Response): Record<string, string> {
  const raw = response["errors"] ?? response["field_errors"];
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
    // Fall back to a single form-level error keyed by the RFC 7807 detail.
    return response.detail ? { _form: response.detail } : {};
  }
  const fieldErrors: Record<string, string> = {};
  for (const [field, message] of Object.entries(raw as Record<string, unknown>)) {
    fieldErrors[field] = String(message);
  }
  return fieldErrors;
}

/**
 * Map an RFC 7807 error response to the DRDP §21.3 UI state descriptor.
 *
 * Unrecognized status codes fall back to the generic server-error state —
 * DRDP §22: "there is no acceptable 'default' that shows blank space".
 * Every mapped error logs `error.mapped` via @reos/logging (WP-002-06 §26).
 */
export function mapErrorToUiState(response: Rfc7807Response): ErrorUiState {
  const status = response.status;
  log.info("error.mapped", { status, code: response.code });

  switch (status) {
    case 400:
    case 422:
      return {
        kind: "form_validation",
        userMessage: USER_MESSAGES[status] ?? "",
        fieldErrors: extractFieldErrors(response),
      };
    case 401:
      return {
        kind: "redirect_sign_in",
        userMessage: USER_MESSAGES[401] ?? "",
        preserveCurrentRoute: true,
      };
    case 403:
      return {
        kind: "permission_denied",
        userMessage: USER_MESSAGES[403] ?? "",
      };
    case 404:
      return {
        kind: "not_found",
        userMessage: USER_MESSAGES[404] ?? "",
        showIllustration: true,
        preserveBreadcrumbs: true,
      };
    case 409:
      return {
        kind: "conflict",
        userMessage: USER_MESSAGES[409] ?? "",
        contextDetail: response.detail ?? "",
      };
    case 429: {
      const retryAfter = Number(response["retry_after"]);
      return {
        kind: "rate_limited",
        userMessage: USER_MESSAGES[429] ?? "",
        retryAfterSeconds:
          Number.isFinite(retryAfter) && retryAfter > 0
            ? retryAfter
            : DEFAULT_RETRY_AFTER_SECONDS,
      };
    }
    case 503:
      return {
        kind: "maintenance",
        userMessage: USER_MESSAGES[503] ?? "",
      };
    case 500:
    default:
      // 500 and anything unmapped: generic state, error_id only (§25).
      return {
        kind: "server_error",
        userMessage: USER_MESSAGES[500] ?? "",
        errorId:
          typeof response["error_id"] === "string"
            ? (response["error_id"] as string)
            : null,
      };
  }
}
