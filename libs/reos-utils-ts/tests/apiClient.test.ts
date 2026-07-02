/**
 * Unit tests for ReosApiClient — WP-002-08 §29, §33.
 *
 * Auth header attached when a token is present; mock 404 routed through
 * mapErrorToUiState; request metadata logged without bodies.
 */

import { setTransport } from "@reos/logging";
import type { LogEntry, Transport } from "@reos/logging";

import { ReosApiClient, ReosApiError } from "../src/apiClient";

class MockTransport implements Transport {
  entries: LogEntry[] = [];
  send(entry: LogEntry): void {
    this.entries.push(entry);
  }
}

function mockFetch(
  status: number,
  body: unknown,
): jest.MockedFunction<typeof fetch> {
  return jest.fn(async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  ) as jest.MockedFunction<typeof fetch>;
}

const BASE = "https://api.test.local";

describe("ReosApiClient", () => {
  let transport: MockTransport;

  beforeEach(() => {
    transport = new MockTransport();
    setTransport(transport);
  });

  it("attaches the Bearer token when the token source provides one", async () => {
    const fetchFn = mockFetch(200, { ok: true });
    const client = new ReosApiClient({
      baseUrl: BASE,
      tokenSource: () => "tok-123",
      fetchFn,
    });
    await client.get("/api/v1/things");
    const [, init] = fetchFn.mock.calls[0]!;
    expect((init?.headers as Record<string, string>)["Authorization"]).toBe(
      "Bearer tok-123",
    );
  });

  it("omits the Authorization header when signed out", async () => {
    const fetchFn = mockFetch(200, { ok: true });
    const client = new ReosApiClient({ baseUrl: BASE, fetchFn });
    await client.get("/x");
    const [, init] = fetchFn.mock.calls[0]!;
    expect(
      (init?.headers as Record<string, string>)["Authorization"],
    ).toBeUndefined();
  });

  it("routes a 404 through mapErrorToUiState (WP-002-06)", async () => {
    const fetchFn = mockFetch(404, {
      type: "https://errors.re-os.dev/resource_not_found",
      title: "Customer was not found.",
      status: 404,
      detail: "Customer with id '7' was not found.",
      instance: "/customers/7",
      code: "RESOURCE_NOT_FOUND",
    });
    const client = new ReosApiClient({ baseUrl: BASE, fetchFn });
    await expect(client.get("/customers/7")).rejects.toThrow(ReosApiError);
    try {
      await client.get("/customers/7");
    } catch (err) {
      const apiError = err as ReosApiError;
      expect(apiError.status).toBe(404);
      expect(apiError.uiState.kind).toBe("not_found");
    }
  });

  it("returns parsed JSON on success", async () => {
    const fetchFn = mockFetch(200, { id: 7, name: "x" });
    const client = new ReosApiClient({ baseUrl: BASE, fetchFn });
    await expect(client.get("/things/7")).resolves.toEqual({ id: 7, name: "x" });
  });

  it("logs request metadata without bodies (§26)", async () => {
    const fetchFn = mockFetch(200, { secretPayload: "do-not-log" });
    const client = new ReosApiClient({ baseUrl: BASE, fetchFn });
    await client.post("/things", { secretBody: "do-not-log-either" });
    const apiLogs = transport.entries.filter((e) => e.event === "api.request");
    expect(apiLogs).toHaveLength(1);
    const serialized = JSON.stringify(apiLogs[0]);
    expect(serialized).toContain('"status":200');
    expect(serialized).not.toContain("do-not-log");
  });
});
