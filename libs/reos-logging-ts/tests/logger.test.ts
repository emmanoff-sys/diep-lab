/**
 * Unit tests for @reos/logging — WP-002-04 §29.
 *
 * Covers: console transport selected in local env; mock remote transport
 * called in non-local envs; severity levels; stateTransition helper shape.
 */

import { configureLogging, log, setTransport } from "../src/logger";
import type { LogEntry, Transport } from "../src/transport";

class MockTransport implements Transport {
  entries: LogEntry[] = [];
  send(entry: LogEntry): void {
    this.entries.push(entry);
  }
}

describe("configureLogging transport selection", () => {
  it("uses the provided remote transport in non-local environments", () => {
    const remote = new MockTransport();
    configureLogging("staging", remote);
    log.info("auth.session_expired", { userId: "u-1" });
    expect(remote.entries).toHaveLength(1);
    expect(remote.entries[0]?.event).toBe("auth.session_expired");
  });

  it("ignores the remote transport in local environment (console used)", () => {
    const remote = new MockTransport();
    const consoleSpy = jest.spyOn(console, "log").mockImplementation(() => {});
    configureLogging("local", remote);
    log.info("dev.event");
    expect(remote.entries).toHaveLength(0);
    expect(consoleSpy).toHaveBeenCalled();
    consoleSpy.mockRestore();
  });
});

describe("log severity levels", () => {
  let transport: MockTransport;

  beforeEach(() => {
    transport = new MockTransport();
    setTransport(transport);
  });

  it("records debug/info/warn levels with context", () => {
    log.debug("a.b", { x: 1 });
    log.info("c.d", { y: 2 });
    log.warn("e.f");
    expect(transport.entries.map((e) => e.level)).toEqual([
      "debug",
      "info",
      "warn",
    ]);
    expect(transport.entries[0]?.context).toEqual({ x: 1 });
  });

  it("records error level with an error object", () => {
    const boom = new Error("boom");
    log.error("request.error", { status: 500 }, boom);
    expect(transport.entries[0]?.level).toBe("error");
    expect(transport.entries[0]?.error).toBe(boom);
  });

  it("stamps an ISO-8601 timestamp on every entry", () => {
    log.info("t.s");
    expect(transport.entries[0]?.timestamp).toMatch(
      /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/,
    );
  });
});

describe("stateTransition helper (DRDP §22)", () => {
  it("emits ui.state_transition with component and states", () => {
    const transport = new MockTransport();
    setTransport(transport);
    log.stateTransition("ProjectList", "loading", "error");
    const entry = transport.entries[0];
    expect(entry?.event).toBe("ui.state_transition");
    expect(entry?.context).toEqual({
      component: "ProjectList",
      fromState: "loading",
      toState: "error",
    });
  });
});
