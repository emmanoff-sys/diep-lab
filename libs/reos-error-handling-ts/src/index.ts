/**
 * @reos/error-handling public API — WP-002-06.
 *
 * Usage: `import { mapErrorToUiState, ReosErrorBoundary } from "@reos/error-handling";`
 */

export { ReosErrorBoundary } from "./ErrorBoundary";
export type { ReosErrorBoundaryProps } from "./ErrorBoundary";
export { mapErrorToUiState } from "./mapError";
export type { ErrorUiState, Rfc7807Response } from "./mapError";
export { USER_MESSAGES } from "./messages";
