import * as React from "react";
import { ShieldCheck } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Field } from "@/components/Field";
import { useFeedbackMutations } from "./useFeedback";
import { humanize } from "@/lib/enums";
import { notifyError, notifySuccess } from "@/lib/toast";

/**
 * Shared 360 give-feedback dialog. Surfaces the safety contract to the giver:
 * their feedback is anonymised to the subject, and a relationship group is only
 * shown once it reaches the minimum volume (default ≥3) — so no one can be
 * de-anonymised by a small group.
 */
export function GiveFeedbackDialog({
  open,
  onOpenChange,
  cycleId,
  relationship,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  cycleId: string | null;
  relationship?: string;
}) {
  const { give } = useFeedbackMutations();
  const [body, setBody] = React.useState("");
  const [sensitive, setSensitive] = React.useState(false);

  React.useEffect(() => {
    if (open) { setBody(""); setSensitive(false); }
  }, [open]);

  async function submit() {
    if (!cycleId || !body.trim()) return;
    try {
      await give.mutateAsync({ cycleId, body: body.trim(), marked_sensitive: sensitive });
      notifySuccess("Feedback submitted", "Thank you — it's recorded anonymously.");
      onOpenChange(false);
    } catch (err) {
      notifyError(err);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Give feedback</DialogTitle>
          <DialogDescription>
            {relationship ? `You were invited as a ${humanize(relationship)} reviewer.` : "Share your feedback."}
          </DialogDescription>
        </DialogHeader>

        <Alert variant="info" className="mb-1">
          <ShieldCheck />
          <AlertDescription>
            Your response is <strong>anonymised</strong> — the subject never sees who said what. A
            relationship group is only shown once it reaches the minimum volume (≥3 responses), so a
            small group can't be de-anonymised.
          </AlertDescription>
        </Alert>

        <Field label="Your feedback" required>
          <Textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="Specific, constructive, behaviour-based…"
            className="min-h-32"
          />
        </Field>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <Checkbox checked={sensitive} onCheckedChange={(c) => setSensitive(Boolean(c))} />
          Flag as sensitive (routes the summary to an HRBP before any release)
        </label>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} loading={give.isPending} disabled={!body.trim()}>
            Submit feedback
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
