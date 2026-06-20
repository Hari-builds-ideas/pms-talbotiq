import { AlertTriangle, Loader2, Sparkles } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { AIJob } from "@/lib/types";

/** Calm copy for each graceful-degrade reason — AI is assistive, never required,
 *  so these read as a state, not an error. */
const DEGRADED_COPY: Record<string, { title: string; body: string }> = {
  NOT_CONFIGURED: {
    title: "AI assistant unavailable",
    body: "The AI assistant isn't configured yet — the manual path is always available.",
  },
  BUDGET_EXCEEDED: {
    title: "AI budget reached",
    body: "This workspace's AI budget for now is used up. Try again later, or upgrade the plan.",
  },
  ANONYMITY_HOLD: {
    title: "Held for anonymity",
    body: "The summary is held for HRBP review to protect contributor anonymity — this is expected, not an error.",
  },
};

/**
 * The shared status surface for an async AI job: a working spinner while
 * QUEUED/RUNNING, a calm assistive banner on DEGRADED, a recoverable error on
 * FAILED, and nothing on SUCCEEDED (the caller re-fetches the artifact to show
 * the real result). `onRetry` re-fires the action; it's hidden for the
 * anonymity hold (re-running won't change the outcome).
 */
export function AIJobBanner({
  job,
  working,
  onRetry,
}: {
  job?: AIJob | null;
  working?: string;
  onRetry?: () => void;
}) {
  if (!job) return null;

  if (job.status === "QUEUED" || job.status === "RUNNING") {
    return (
      <Alert variant="ai">
        <Loader2 className="animate-spin" />
        <AlertTitle>{working ?? "AI is working…"}</AlertTitle>
        <AlertDescription>This updates automatically when it's ready.</AlertDescription>
      </Alert>
    );
  }

  if (job.status === "DEGRADED") {
    const copy = DEGRADED_COPY[job.error_code] ?? {
      title: "AI step didn't run",
      body: "The AI step was skipped — the manual path is always available.",
    };
    const canRetry = onRetry && job.error_code !== "ANONYMITY_HOLD";
    return (
      <Alert variant="ai">
        <Sparkles />
        <AlertTitle>{copy.title}</AlertTitle>
        <AlertDescription className="space-y-2">
          <p>{copy.body}</p>
          {canRetry && (
            <Button variant="outline" size="sm" onClick={onRetry}>
              Try again
            </Button>
          )}
        </AlertDescription>
      </Alert>
    );
  }

  if (job.status === "FAILED") {
    return (
      <Alert variant="danger">
        <AlertTriangle />
        <AlertTitle>AI step failed</AlertTitle>
        <AlertDescription className="space-y-2">
          <p>Something went wrong running the AI step. You can try again.</p>
          {onRetry && (
            <Button variant="outline" size="sm" onClick={onRetry}>
              Try again
            </Button>
          )}
        </AlertDescription>
      </Alert>
    );
  }

  return null; // SUCCEEDED — the artifact refetch shows the result
}
