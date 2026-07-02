/**
 * Unit tests for mapErrorToUiState — WP-002-06 §29.
 *
 * All 9 DRDP §21.3 status codes produce the specified ErrorUiState shape.
 * NOTE: message-copy equality against DRDP §21.3 is BLOCKED ON ECR-002-06-01
 * (copy not available in-repo) — these tests assert shape and behavior, and
 * that every state carries a non-empty userMessage (no blank states, §22).
 */

import { setTransport } from "@reos/logging";
import type { LogEntry, Transport } from "@reos/logging";

import { mapErrorToUiState } from "../src/mapError";
import type { Rfc7807Response } from "../src/mapError";

class MockTransport implements Transport {
  entries: LogEntry[] = [];
  send(entry: LogEntry): void {
    this.entries.push(entry);
  }
}

let transport: MockTransport;

beforeEach(() => {
  transport = new MockTransport();
  setTransport(transport);
});

function rfc7807(status: number, extra: Record<string, unknown> = {}): Rfc7807Response {
  return { status, title: "t", detail: "d", instance: "/x", ...extra };
}

describe("mapErrorToUiState — all 9 DRDP §21.3 status codes", () => {
  it("400 → form_validation with field errors", () => {
    const state = mapErrorToUiState(
      rfc7807(400, { errors: { name: "required" } }),
    );
    expect(state.kind).toBe("form_validation");
    if (state.kind === "form_validation") {
      expect(state.fieldErrors).toEqual({ name: "required" });
    }
  });

  it("422 → form_validation; falls back to detail when no field map", () => {
    const state = mapErrorToUiState(rfc7807(422, { detail: "kwp must be positive" }));
    expect(state.kind).toBe("form_validation");
    if (state.kind === "form_validation") {
      expect(state.fieldErrors).toEqual({ _form: "kwp must be positive" });
    }
  });

  it("401 → redirect_sign_in preserving the current route", () => {
    const state = mapErrorToUiState(rfc7807(401));
    expect(state.kind).toBe("redirect_sign_in");
    if (state.kind === "redirect_sign_in") {
      expect(state.preserveCurrentRoute).toBe(true);
    }
  });

  it("403 → permission_denied (not a blank screen)", () => {
    const state = mapErrorToUiState(rfc7807(403));
    expect(state.kind).toBe("permission_denied");
    expect(state.userMessage.length).toBeGreaterThan(0);
  });

  it("404 → not_found with illustration and preserved breadcrumbs", () => {
    const state = mapErrorToUiState(rfc7807(404));
    expect(state.kind).toBe("not_found");
    if (state.kind === "not_found") {
      expect(state.showIllustration).toBe(true);
      expect(state.preserveBreadcrumbs).toBe(true);
    }
  });

  it("409 → conflict carrying the context-specific detail", () => {
    const state = mapErrorToUiState(rfc7807(409, { detail: "version already published" }));
    expect(state.kind).toBe("conflict");
    if (state.kind === "conflict") {
      expect(state.contextDetail).toBe("version already published");
    }
  });

  it("429 → rate_limited with countdown from retry_after", () => {
    const state = mapErrorToUiState(rfc7807(429, { retry_after: 12 }));
    expect(state.kind).toBe("rate_limited");
    if (state.kind === "rate_limited") {
      expect(state.retryAfterSeconds).toBe(12);
    }
  });

  it("429 without retry_after uses a sane default countdown", () => {
    const state = mapErrorToUiState(rfc7807(429));
    if (state.kind === "rate_limited") {
      expect(state.retryAfterSeconds).toBeGreaterThan(0);
    }
  });

  it("500 → server_error surfacing only the error_id", () => {
    const state = mapErrorToUiState(
      rfc7807(500, { error_id: "err-abc-123", stack: "Traceback ..." }),
    );
    expect(state.kind).toBe("server_error");
    if (state.kind === "server_error") {
      expect(state.errorId).toBe("err-abc-123");
      expect(JSON.stringify(state)).not.toContain("Traceback");
    }
  });

  it("503 → maintenance descriptor", () => {
    const state = mapErrorToUiState(rfc7807(503));
    expect(state.kind).toBe("maintenance");
  });
});

describe("resilience and observability", () => {
  it("unknown status falls back to server_error — never blank (DRDP §22)", () => {
    const state = mapErrorToUiState(rfc7807(418));
    expect(state.kind).toBe("server_error");
    expect(state.userMessage.length).toBeGreaterThan(0);
  });

  it("every mapped error logs error.mapped with the original status", () => {
    mapErrorToUiState(rfc7807(404));
    expect(transport.entries).toHaveLength(1);
    expect(transport.entries[0]?.event).toBe("error.mapped");
    expect(transport.entries[0]?.context).toMatchObject({ status: 404 });
  });

  it("every state carries a non-empty userMessage", () => {
    for (const status of [400, 401, 403, 404, 409, 422, 429, 500, 503]) {
      expect(mapErrorToUiState(rfc7807(status)).userMessage.length).toBeGreaterThan(0);
    }
  });
});
