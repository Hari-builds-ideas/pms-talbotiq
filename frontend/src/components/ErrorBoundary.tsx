import * as React from "react";
import { AlertTriangle, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  children: React.ReactNode;
  /** Remounts the boundary when this key changes (e.g. the route path), so
   * navigating away from a crashed screen clears the error automatically. */
  resetKey?: string;
}
interface State {
  error: Error | null;
}

/**
 * Global render error boundary. A thrown error in any screen renders a calm,
 * branded fallback (not a white screen) and keeps the app shell usable — the
 * user can retry or navigate elsewhere. Network/API errors are handled by the
 * error-code mapper + ErrorState; this catches genuine render/programming faults.
 */
export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidUpdate(prev: Props) {
    // Auto-clear when the reset key (route) changes.
    if (this.state.error && prev.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Surface to the console for debugging; no telemetry sink in this build.
    // eslint-disable-next-line no-console
    console.error("Render error caught by ErrorBoundary:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-[60vh] flex-col items-center justify-center px-6 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-danger-subtle">
            <AlertTriangle className="h-6 w-6 text-danger" />
          </div>
          <h2 className="mt-4 text-lg font-semibold">Something went wrong</h2>
          <p className="mt-1 max-w-md text-sm text-muted-foreground">
            This screen hit an unexpected error. You can retry, or use the navigation to move
            elsewhere — the rest of the app is still working.
          </p>
          <p className="mt-2 max-w-md truncate font-mono text-2xs text-muted-foreground/70">
            {this.state.error.message}
          </p>
          <Button className="mt-4" onClick={() => this.setState({ error: null })}>
            <RotateCw className="h-4 w-4" /> Try again
          </Button>
        </div>
      );
    }
    return this.props.children;
  }
}
