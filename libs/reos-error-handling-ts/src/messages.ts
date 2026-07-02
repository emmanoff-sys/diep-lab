/**
 * User-facing message copy — ⚠️ PLACEHOLDER PENDING ECR-002-06-01 ⚠️
 *
 * DRDP v1.0 §21.3's "User Message (plain language)" column is the approved
 * design artifact for this copy, and the full DRDP text is maintained
 * EXTERNALLY (the in-repo `docs/architecture/drdp.md` is a different
 * document — Data Retention and Destruction Policy — acronym collision).
 *
 * Per WP-002-06 §39, this copy must NOT be paraphrased or invented ad hoc.
 * The strings below are engineering placeholders so the mapping logic is
 * testable; they MUST be replaced verbatim from DRDP v1.0 §21.3 when
 * ECR-002-06-01 is resolved. Do not ship any app using these placeholders.
 */

export const USER_MESSAGES: Record<number, string> = {
  400: "[PLACEHOLDER ECR-002-06-01] Please check the highlighted fields and try again.",
  401: "[PLACEHOLDER ECR-002-06-01] Your session has ended. Please sign in again.",
  403: "[PLACEHOLDER ECR-002-06-01] You don't have permission to view this.",
  404: "[PLACEHOLDER ECR-002-06-01] We couldn't find what you were looking for.",
  409: "[PLACEHOLDER ECR-002-06-01] This item was changed elsewhere. Please review and retry.",
  422: "[PLACEHOLDER ECR-002-06-01] Please check the highlighted fields and try again.",
  429: "[PLACEHOLDER ECR-002-06-01] Too many requests. Please wait and try again.",
  500: "[PLACEHOLDER ECR-002-06-01] Something went wrong on our side.",
  503: "[PLACEHOLDER ECR-002-06-01] The service is temporarily unavailable.",
};
