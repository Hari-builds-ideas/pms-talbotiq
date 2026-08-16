import { Ban, CircleSlash, CloudOff, Gauge } from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth } from "@/lib/auth/AuthContext";
import { cn } from "@/lib/utils";

/** The four states the server distinguishes (B3, apps/ai/http.py). */
export type AIUnavailableCode =
  | "ai_disabled"
  | "ai_not_configured"
  | "ai_budget_exhausted"
  | "ai_provider_error";

/**
 * Pull the AI state out of a caught API error.
 *
 * Returns null when this was not an AI-availability problem, so a caller can
 * fall through to its ordinary error handling rather than mislabelling, say, a
 * 403 as "AI unavailable".
 */
export function aiUnavailableCode(err: unknown): AIUnavailableCode | null {
  const body = (err as { response?: { data?: { code?: string } } })?.response?.data;
  const code = body?.code;
  if (
    code === "ai_disabled" ||
    code === "ai_not_configured" ||
    code === "ai_budget_exhausted" ||
    code === "ai_provider_error"
  ) {
    return code;
  }
  return null;
}

interface Copy {
  icon: typeof Ban;
  title: string;
  /** What happened, and what the reader can do about it. */
  body: string;
  /** Only shown to someone who can actually act on it. */
  adminHint?: string;
  tone: string;
}

const COPY: Record<AIUnavailableCode, Copy> = {
  ai_disabled: {
    icon: Ban,
    title: "AI is switched off here",
    body: "Your organisation has turned AI features off. Nothing you type is sent to a model provider.",
    adminHint: "You can turn it back on in Administration → AI.",
    tone: "text-muted-foreground",
  },
  ai_not_configured: {
    icon: CircleSlash,
    title: "AI isn't set up yet",
    body: "No model provider has been connected for this organisation, so AI features can't run.",
    adminHint: "Add a provider key in Administration → AI.",
    tone: "text-muted-foreground",
  },
  ai_budget_exhausted: {
    icon: Gauge,
    title: "AI budget used up",
    body: "This period's AI budget has been reached. It resets automatically — everything else keeps working.",
    adminHint: "You can review usage and raise the limit in Administration → AI.",
    tone: "text-warning",
  },
  ai_provider_error: {
    icon: CloudOff,
    title: "The AI provider didn't respond",
    body: "Nothing was changed. This is usually temporary — try again in a moment.",
    tone: "text-warning",
  },
};

/**
 * The one place an unavailable AI feature is explained.
 *
 * Before this, all four causes arrived as the same generic "AI isn't available",
 * which tells the reader nothing about whether to call their admin, wait for the
 * budget to reset, or just retry. Each state now says which it is, and the
 * admin-only line is shown only to someone who can act on it — telling an
 * employee to go and change a setting they cannot reach is worse than saying
 * nothing.
 */
export function AIUnavailable({
  code,
  className,
  compact = false,
}: {
  code: AIUnavailableCode;
  className?: string;
  /** Inline variant for a tile or a panel corner, rather than a full block. */
  compact?: boolean;
}) {
  const { atLeast } = useAuth();
  const copy = COPY[code];
  const Icon = copy.icon;
  const isAdmin = atLeast("ADMIN");

  if (compact) {
    return (
      <p className={cn("flex items-start gap-2 text-xs text-muted-foreground", className)}>
        <Icon className={cn("mt-0.5 h-3.5 w-3.5 shrink-0", copy.tone)} />
        <span>
          {copy.body}
          {isAdmin && copy.adminHint ? ` ${copy.adminHint}` : ""}
        </span>
      </p>
    );
  }

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-lg border border-border bg-card px-6 py-8 text-center",
        className,
      )}
      role="status"
    >
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-secondary">
        <Icon className={cn("h-5 w-5", copy.tone)} />
      </div>
      <h3 className="text-sm font-semibold text-foreground">{copy.title}</h3>
      <p className="max-w-sm text-sm text-muted-foreground">{copy.body}</p>
      {isAdmin && copy.adminHint && (
        <Link
          to="/admin/ai"
          className="tap-target text-sm font-medium text-primary hover:underline"
        >
          {copy.adminHint}
        </Link>
      )}
    </div>
  );
}
