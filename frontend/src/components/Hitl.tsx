import { AlertTriangle, FileWarning, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { formatConfidence } from "@/lib/format";
import { LOW_CONFIDENCE_THRESHOLD } from "@/lib/enums";
import { cn } from "@/lib/utils";

/** "Draft — pending review" chip. Never let a draft read as final. */
export function DraftBadge({ className }: { className?: string }) {
  return (
    <Badge variant="warning" className={cn("gap-1", className)}>
      <FileWarning className="h-3 w-3" />
      Draft — pending review
    </Badge>
  );
}

/** Provenance chip — AI / MANUAL / DETERMINISTIC. */
export function SourceBadge({ source }: { source?: string | null }) {
  if (!source) return null;
  if (source === "AI") {
    return (
      <Badge variant="ai" className="gap-1">
        <Sparkles className="h-3 w-3" /> AI-generated
      </Badge>
    );
  }
  return <Badge variant="muted">{source === "DETERMINISTIC" ? "Deterministic" : "Manual"}</Badge>;
}

interface ConfidenceBadgeProps {
  score?: string | number | null;
  className?: string;
}

/** Confidence chip; flips to a warning treatment below the low threshold. */
export function ConfidenceBadge({ score, className }: ConfidenceBadgeProps) {
  if (score === null || score === undefined || score === "") return null;
  const n = typeof score === "number" ? score : Number(score);
  if (Number.isNaN(n)) return null;
  const low = n < LOW_CONFIDENCE_THRESHOLD;
  return (
    <Badge variant={low ? "danger" : "info"} className={cn("gap-1 tabular-nums", className)}>
      {low && <AlertTriangle className="h-3 w-3" />}
      Confidence {formatConfidence(n)}
    </Badge>
  );
}

interface HitlBannerProps {
  /** AI confidence (0–1) if the artifact carries one. */
  confidence?: string | number | null;
  source?: string | null;
  /** Custom lead text; defaults to the standard HITL message. */
  message?: string;
  className?: string;
}

/**
 * The HITL banner shown above any pending AI/automated artifact. Elevates a
 * low-confidence warning. Render this on review / summary / plan / JD surfaces
 * whenever the entity is in a PENDING_HUMAN_REVIEW-style state.
 */
export function HitlBanner({
  confidence,
  source,
  message,
  className,
}: HitlBannerProps) {
  const n =
    confidence === null || confidence === undefined || confidence === ""
      ? null
      : typeof confidence === "number"
        ? confidence
        : Number(confidence);
  const low = n != null && !Number.isNaN(n) && n < LOW_CONFIDENCE_THRESHOLD;

  return (
    <Alert variant={low ? "danger" : "ai"} className={className}>
      {low ? <AlertTriangle /> : <Sparkles />}
      <AlertTitle>
        {low ? "Low-confidence draft — review carefully" : "Pending human review"}
      </AlertTitle>
      <AlertDescription className="flex flex-col gap-2">
        <span>
          {message ??
            "This is a draft awaiting a human decision. Approve, reject, or edit before it becomes final — it is never published automatically."}
        </span>
        <span className="flex flex-wrap items-center gap-2">
          <SourceBadge source={source} />
          <ConfidenceBadge score={confidence} />
        </span>
      </AlertDescription>
    </Alert>
  );
}
