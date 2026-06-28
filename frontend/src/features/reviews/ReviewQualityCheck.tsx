import * as React from "react";
import { useMutation } from "@tanstack/react-query";
import { Check, Sparkles, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { aiApi } from "@/lib/api/endpoints";
import { mapApiError } from "@/lib/errors";
import { humanize } from "@/lib/enums";
import { notifyError } from "@/lib/toast";
import type { ReviewQualityFlag } from "@/lib/types";

/**
 * RW_BUILD_5 quick win #2 — an ASSISTIVE AI check over the draft review text the
 * reviewer is editing. It flags possible recency bias, harsh wording, missing
 * evidence or vagueness as **dismissable, non-blocking** advisory chips. It NEVER
 * blocks submitting (the Save/Submit buttons are unaffected) and persists nothing.
 *
 * Manager+ only (gated by the caller). Errors are kind-aware: a missing provider
 * (503) or exhausted budget (429) render inline; anything else toasts.
 */
export function ReviewQualityCheck({ text }: { text: string }) {
  const [flags, setFlags] = React.useState<ReviewQualityFlag[] | null>(null);
  const [dismissed, setDismissed] = React.useState<Set<number>>(new Set());
  const [unavailable, setUnavailable] = React.useState<string | null>(null);

  const m = useMutation({
    mutationFn: (t: string) => aiApi.reviewQuality(t),
    onSuccess: (res) => {
      setFlags(res.flags);
      setDismissed(new Set());
      setUnavailable(null);
    },
    onError: (err) => {
      const mapped = mapApiError(err);
      setFlags(null);
      if (mapped.kind === "ai_unavailable" || mapped.kind === "rate_limited") {
        setUnavailable(mapped.message);
      } else {
        notifyError(err);
      }
    },
  });

  function check() {
    const t = text.trim();
    if (!t) return;
    setUnavailable(null);
    m.mutate(t);
  }

  const remaining = flags?.filter((_, i) => !dismissed.has(i)) ?? [];

  return (
    <div className="space-y-2 rounded-md border border-ai/20 bg-ai-subtle/30 p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Sparkles className="h-3.5 w-3.5 text-ai" />
          AI quality check — advisory only; it never blocks submitting.
        </span>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={check}
          loading={m.isPending}
          disabled={!text.trim()}
        >
          <Sparkles className="h-3.5 w-3.5 text-ai" /> Check with AI
        </Button>
      </div>

      {unavailable && (
        <Alert variant="ai">
          <Sparkles />
          <AlertTitle>AI check unavailable</AlertTitle>
          <AlertDescription>{unavailable}</AlertDescription>
        </Alert>
      )}

      {flags !== null && !unavailable && (
        remaining.length === 0 ? (
          <p className="flex items-center gap-1.5 text-xs text-success">
            <Check className="h-3.5 w-3.5" />
            {flags.length === 0
              ? "No issues flagged — reads balanced and specific."
              : "All suggestions dismissed."}
          </p>
        ) : (
          <ul className="space-y-1.5">
            {flags.map((f, i) =>
              dismissed.has(i) ? null : (
                <li
                  key={i}
                  className="flex items-start gap-2 rounded-md border border-warning/30 bg-warning-subtle/40 px-2.5 py-1.5 text-xs"
                >
                  <Badge variant="warning" className="shrink-0">{humanize(f.type)}</Badge>
                  <span className="flex-1 text-foreground">{f.note}</span>
                  <button
                    type="button"
                    aria-label="Dismiss suggestion"
                    onClick={() => setDismissed((d) => new Set(d).add(i))}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </li>
              ),
            )}
          </ul>
        )
      )}
    </div>
  );
}
