import {
  AlertTriangle,
  Ban,
  Clock,
  Lock,
  RefreshCw,
  SearchX,
  Sparkles,
  WifiOff,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { mapApiError, type ApiError, type ApiErrorKind } from "@/lib/errors";
import { cn } from "@/lib/utils";

interface ErrorStateProps {
  error: unknown;
  /** Re-run the query. */
  onRetry?: () => void;
  /** For 404 — go back to the list (the "not yours / not there" rule). */
  onBack?: () => void;
  className?: string;
  compact?: boolean;
}

const KIND_META: Record<
  ApiErrorKind,
  { icon: LucideIcon; title: string; tone: string }
> = {
  bad_input: { icon: AlertTriangle, title: "Check your input", tone: "text-warning" },
  unauthenticated: { icon: Lock, title: "Session expired", tone: "text-warning" },
  forbidden: { icon: Ban, title: "Not permitted", tone: "text-danger" },
  not_found: { icon: SearchX, title: "Not found", tone: "text-muted-foreground" },
  conflict: { icon: RefreshCw, title: "This changed", tone: "text-warning" },
  domain: { icon: AlertTriangle, title: "Can't do that yet", tone: "text-warning" },
  rate_limited: { icon: Clock, title: "Usage limit reached", tone: "text-warning" },
  ai_unavailable: { icon: Sparkles, title: "AI not available yet", tone: "text-ai" },
  network: { icon: WifiOff, title: "Connection problem", tone: "text-danger" },
  unknown: { icon: AlertTriangle, title: "Something went wrong", tone: "text-danger" },
};

/** Renders the right friendly state for any API error code. */
export function ErrorState({
  error,
  onRetry,
  onBack,
  className,
  compact,
}: ErrorStateProps) {
  const mapped: ApiError = mapApiError(error);
  const meta = KIND_META[mapped.kind];
  const Icon = meta.icon;

  const showRetry =
    onRetry &&
    (mapped.kind === "network" ||
      mapped.kind === "unknown" ||
      mapped.kind === "conflict");
  const showBack = onBack && mapped.kind === "not_found";

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-lg border border-border bg-card text-center",
        compact ? "gap-2 px-6 py-10" : "gap-3 px-6 py-14",
        className,
      )}
      role="alert"
    >
      <div className={cn("flex h-11 w-11 items-center justify-center rounded-full bg-secondary", meta.tone)}>
        <Icon className="h-5 w-5" aria-hidden />
      </div>
      <div className="space-y-1">
        <p className="text-md font-semibold text-foreground">{meta.title}</p>
        <p className="mx-auto max-w-md text-sm text-muted-foreground">
          {mapped.message}
          {mapped.code && (
            <span className="ml-1 font-mono text-2xs text-muted-foreground/70">
              ({mapped.code})
            </span>
          )}
        </p>
        {mapped.kind === "rate_limited" && mapped.retryAfter != null && (
          <p className="text-xs text-muted-foreground">
            Try again in ~{mapped.retryAfter}s.
          </p>
        )}
      </div>
      {(showRetry || showBack) && (
        <div className="mt-1 flex gap-2">
          {showRetry && (
            <Button variant="outline" size="sm" onClick={onRetry}>
              <RefreshCw className="h-4 w-4" />
              Retry
            </Button>
          )}
          {showBack && (
            <Button variant="outline" size="sm" onClick={onBack}>
              Back to list
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
