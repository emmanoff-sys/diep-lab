/**
 * <ReosErrorBoundary> — React error boundary rendering DRDP §22-compliant
 * error states instead of blank screens or raw stack traces.
 *
 * Authority: WP-002-06 | DRDP v1.0 §22 (Error state — "no acceptable
 * 'default' that shows blank space").
 */

import * as React from "react";

import { log } from "@reos/logging";

import { USER_MESSAGES } from "./messages";

export interface ReosErrorBoundaryProps {
  children: React.ReactNode;
  /**
   * Render prop for the error state. Receives the generic user message —
   * NEVER the raw error (security: WP-002-06 §25). Defaults to a minimal
   * accessible fallback so no consumer can accidentally render blank space.
   */
  fallback?: (userMessage: string) => React.ReactNode;
}

interface ReosErrorBoundaryState {
  hasError: boolean;
}

export class ReosErrorBoundary extends React.Component<
  ReosErrorBoundaryProps,
  ReosErrorBoundaryState
> {
  constructor(props: ReosErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): ReosErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    log.error("ui.render_error", { componentStack: errorInfo.componentStack }, error);
  }

  render(): React.ReactNode {
    if (this.state.hasError) {
      const userMessage = USER_MESSAGES[500] ?? "";
      if (this.props.fallback) {
        return this.props.fallback(userMessage);
      }
      return <div role="alert">{userMessage}</div>;
    }
    return this.props.children;
  }
}
