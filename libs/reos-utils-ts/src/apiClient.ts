/**
 * ReosApiClient — the governed API client for the DAEP / RE-OS web portal.
 *
 * Authority: WP-002-08 | DRDP v1.0 §23.2 (`lib/api/` client layer).
 *
 * Every network call goes through this client: it attaches the Bearer token
 * (when a token source is wired), logs request metadata, and routes every
 * non-2xx response through mapErrorToUiState (WP-002-06) — no consuming
 * screen ever hand-parses an error response.
 *
 * Security (WP-002-08 §25): token *retrieval/storage* is OUT OF SCOPE here —
 * `tokenSource` is a hook, not an auth implementation. The real auth feature
 * must supply tokens from secure storage (httpOnly cookie / equivalent).
 * TODO(auth-feature): wire tokenSource from the real auth feature when it
 * ships — this placeholder hook is a documented gap, not a finished feature.
 */

import { getConfig } from "@reos/config";
import { mapErrorToUiState } from "@reos/error-handling";
import type { ErrorUiState, Rfc7807Response } from "@reos/error-handling";
import { log } from "@reos/logging";

/** Hook supplying the current Bearer token, or null when signed out. */
export type TokenSource = () => string | null;

/** Thrown for every non-2xx response, carrying the mapped UI state. */
export class ReosApiError extends Error {
  constructor(
    public readonly uiState: ErrorUiState,
    public readonly status: number,
  ) {
    super(`API request failed with status ${status}`);
    this.name = "ReosApiError";
  }
}

export interface ReosApiClientOptions {
  /** Defaults to `getConfig().apiBaseUrl`. */
  baseUrl?: string;
  /** TODO(auth-feature): supplied by the real auth feature. */
  tokenSource?: TokenSource;
  /** Injectable fetch for tests / non-browser runtimes. */
  fetchFn?: typeof fetch;
}

export class ReosApiClient {
  private readonly baseUrl: string;
  private readonly tokenSource: TokenSource;
  private readonly fetchFn: typeof fetch;

  constructor(options: ReosApiClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? getConfig().apiBaseUrl;
    this.tokenSource = options.tokenSource ?? (() => null);
    this.fetchFn = options.fetchFn ?? fetch;
  }

  async get<T>(path: string): Promise<T> {
    return this.request<T>("GET", path);
  }

  async post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>("POST", path, body);
  }

  async put<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>("PUT", path, body);
  }

  async delete<T>(path: string): Promise<T> {
    return this.request<T>("DELETE", path);
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const headers: Record<string, string> = {
      Accept: "application/json",
    };
    const token = this.tokenSource();
    if (token !== null) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
    }

    const startedAt = Date.now();
    const response = await this.fetchFn(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    // Metadata only — never bodies (PII risk, WP-002-08 §26).
    log.debug("api.request", {
      method,
      url,
      status: response.status,
      durationMs: Date.now() - startedAt,
    });

    if (!response.ok) {
      const problem = (await response
        .json()
        .catch(() => ({ status: response.status }))) as Rfc7807Response;
      problem.status = problem.status ?? response.status;
      throw new ReosApiError(mapErrorToUiState(problem), response.status);
    }
    if (response.status === 204) {
      return undefined as T;
    }
    return (await response.json()) as T;
  }
}
