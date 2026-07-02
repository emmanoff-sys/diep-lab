/**
 * User-facing message copy — APPROVED (ECR-002-06-01 resolved).
 *
 * Authority: `docs/architecture/UI_MESSAGE_SPEC.md` §3 — the single source
 * of truth for this copy (resolves ECR-002-06-01, which was raised when the
 * DRDP v1.0 §21.3 copy was unavailable in-repo).
 *
 * Per WP-002-06 §39, this copy must NOT be paraphrased or edited ad hoc.
 * Any wording change requires UI/UX design sign-off and an EECR change
 * record — edit `UI_MESSAGE_SPEC.md` first, then mirror the change here and
 * in `libs/reos_error_handling/lib/map_error.dart`.
 *
 * Only the nine status codes routed by `mapError.ts`'s switch/case are keyed
 * here (400/401/403/404/409/422/429/500/503). UI_MESSAGE_SPEC.md §3.9 (502)
 * and §3.11 (Unknown Error) are documented for completeness but are, by
 * design, not separately wired — 502 and any unmapped status fall through to
 * the 500 `server_error` state (see `mapError.ts`'s `default` case).
 */

export const USER_MESSAGES: Record<number, string> = {
  400: "Some of the information provided needs attention. Please check the highlighted fields and try again.",
  401: "Your session has ended. Please sign in again to continue.",
  403: "You don't have permission to view or change this. If you believe you should, contact your administrator.",
  404: "We couldn't find what you were looking for. It may have been moved or removed.",
  409: "This item was changed by someone else while you were working. Please review the latest version and try again.",
  422: "Some of the information provided needs attention. Please check the highlighted fields and try again.",
  429: "You've made too many requests in a short time. Please wait a moment before trying again.",
  500: "Something went wrong on our side. Your data is safe. Please try again, and contact support with the reference code if the problem continues.",
  503: "The service is temporarily unavailable, possibly for maintenance. Please try again shortly.",
};
