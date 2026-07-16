import { AlertTriangle, ShieldCheck, ShieldAlert } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/StatusBadge";
import { ConfidenceBadge, HitlBanner } from "@/components/Hitl";
import { humanize } from "@/lib/enums";
import type { FeedbackSummary } from "@/lib/types";

const SECTION_LABELS: Record<string, string> = {
  strengths: "Strengths",
  growth: "Growth areas",
  themes: "Themes",
  risks: "Risks",
};

/**
 * Renders an Agent-3 feedback summary with its safety properties legible:
 * HRBP_HOLD/breach treatment, anonymity-passed, sensitivity, the volume total
 * and any below-threshold groups that were suppressed from the source. Used by
 * the HRBP review queue and the subject's released view.
 */
export function SummaryView({ summary, showHitl }: { summary: FeedbackSummary; showHitl?: boolean }) {
  const sections = summary.sections;
  const held = summary.status === "HRBP_HOLD";
  const pending = summary.status === "PENDING_HUMAN_REVIEW";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={summary.status} dot />
        <ConfidenceBadge score={summary.confidence_score} />
        {summary.anonymity_passed ? (
          <Badge variant="success" className="gap-1"><ShieldCheck className="h-3 w-3" /> Anonymity passed</Badge>
        ) : (
          <Badge variant="danger" className="gap-1"><ShieldAlert className="h-3 w-3" /> Anonymity flagged</Badge>
        )}
        {summary.sensitive && <Badge variant="warning">Sensitive</Badge>}
        <Badge variant="muted">{summary.volume_total} response{summary.volume_total === 1 ? "" : "s"}</Badge>
      </div>

      {held && (
        <Alert variant="warning">
          <ShieldAlert />
          <AlertTitle>Held for HRBP review</AlertTitle>
          <AlertDescription>
            This summary was held{summary.anonymity_passed ? " (flagged sensitive)" : " — a potential anonymity breach was detected in the generated text"}.
            Review carefully before releasing; it is never auto-released.
          </AlertDescription>
        </Alert>
      )}
      {showHitl && pending && <HitlBanner source="AI" confidence={summary.confidence_score} message="This AI feedback summary is a draft pending your review. Release it to make it visible to the subject — it is never published automatically." />}

      {summary.insufficient_groups.length > 0 && (
        <Alert variant="info">
          <AlertTriangle />
          <AlertTitle>Some groups suppressed for privacy</AlertTitle>
          <AlertDescription>
            {summary.insufficient_groups.map((g) => humanize(g)).join(", ")} had fewer than the minimum
            responses and were excluded so individuals can't be identified.
          </AlertDescription>
        </Alert>
      )}

      {sections ? (
        <div className="space-y-3">
          {(["strengths", "growth", "themes", "risks"] as const).map((key) => (
            <div key={key}>
              <p className="mb-1 text-2xs font-semibold uppercase tracking-wide text-muted-foreground">
                {SECTION_LABELS[key]}
              </p>
              <p className="whitespace-pre-wrap break-words text-sm text-foreground">
                {sections[key] || <span className="text-muted-foreground">—</span>}
              </p>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          Sections haven't been generated yet (the AI summary hasn't run, or was held before generation).
        </p>
      )}
    </div>
  );
}
