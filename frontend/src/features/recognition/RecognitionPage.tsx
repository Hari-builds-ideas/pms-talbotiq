import * as React from "react";
import { Award, Plus, Sparkles, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Field } from "@/components/Field";
import { CardGridSkeleton } from "@/components/Skeletons";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { useAuth } from "@/lib/auth/AuthContext";
import { useDirectory } from "@/lib/hooks/useDirectory";
import { initials } from "@/lib/format";
import { notifyError, notifySuccess } from "@/lib/toast";
import type { RecognitionCard as Card_, RecognitionVisibility } from "@/lib/types";
import {
  useRecognitionFeed,
  useRecognitionMeta,
  useRecognitionMutations,
} from "./useRecognition";

const VISIBILITY_LABEL: Record<RecognitionVisibility, string> = {
  PRIVATE: "Private",
  MANAGER_ONLY: "Manager only",
  TEAM: "Team",
  COMPANY: "Company",
};

export function RecognitionPage() {
  const feed = useRecognitionFeed();
  const [giveOpen, setGiveOpen] = React.useState(false);
  const cards = feed.data ?? [];

  return (
    <div>
      <PageHeader
        eyebrow="Performance" title="Recognition"
        description="Celebrate great work. Recognitions are shared at the visibility you choose — private, manager-only, team, or company-wide."
        actions={
          <Button onClick={() => setGiveOpen(true)}>
            <Plus className="h-4 w-4" /> Give recognition
          </Button>
        }
      />

      {feed.isLoading ? (
        <CardGridSkeleton count={3} />
      ) : feed.isError ? (
        <ErrorState error={feed.error} onRetry={() => feed.refetch()} />
      ) : cards.length === 0 ? (
        <EmptyState
          icon={Sparkles}
          title="No recognitions yet"
          description="Be the first to recognise a teammate for living a company value."
          action={<Button onClick={() => setGiveOpen(true)}>Give the first recognition</Button>}
        />
      ) : (
        <div className="mx-auto max-w-2xl space-y-4">
          {cards.map((c) => (
            <RecognitionItem key={c.id} card={c} />
          ))}
        </div>
      )}

      <GiveRecognitionDialog open={giveOpen} onOpenChange={setGiveOpen} />
    </div>
  );
}

function RecognitionItem({ card }: { card: Card_ }) {
  const meta = useRecognitionMeta();
  const m = useRecognitionMutations();
  const palette = meta.data?.reactions ?? [];

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <Avatar className="h-9 w-9">
              <AvatarFallback>{initials(card.recipient.display)}</AvatarFallback>
            </Avatar>
            <div className="min-w-0 leading-tight">
              <p className="text-sm break-words">
                <span className="font-semibold">{card.sender.display}</span>
                <span className="text-muted-foreground"> recognised </span>
                <span className="font-semibold">{card.recipient.display}</span>
              </p>
              <div className="mt-0.5 flex items-center gap-1.5">
                <Badge variant="secondary" className="gap-1">
                  <Award className="h-3 w-3" /> {card.value}
                </Badge>
                {card.badge && <Badge variant="muted">{card.badge}</Badge>}
                <Badge variant="muted" title="Who can see this">
                  {VISIBILITY_LABEL[card.visibility]}
                </Badge>
              </div>
            </div>
          </div>
          {card.can_delete && (
            <Button
              variant="ghost"
              size="icon-sm"
              className="text-muted-foreground hover:text-danger"
              aria-label="Remove recognition"
              loading={m.remove.isPending}
              onClick={() =>
                m.remove
                  .mutateAsync(card.id)
                  .then(() => notifySuccess("Recognition removed"))
                  .catch(notifyError)
              }
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          )}
        </div>

        <p className="whitespace-pre-line break-words text-sm text-foreground">{card.message}</p>

        <div className="flex flex-wrap items-center gap-1.5 pt-1">
          {palette.map((emoji) => {
            const count = card.reactions.counts[emoji] ?? 0;
            const mine = card.reactions.mine.includes(emoji);
            return (
              <button
                key={emoji}
                type="button"
                onClick={() =>
                  m.react.mutateAsync({ id: card.id, emoji }).catch(notifyError)
                }
                aria-pressed={mine}
                aria-label={`React ${emoji}`}
                className={`tap-target inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs transition-colors ${
                  mine
                    ? "border-primary/40 bg-primary/10 text-foreground"
                    : "border-border bg-card text-muted-foreground hover:bg-secondary"
                }`}
              >
                <span>{emoji}</span>
                {count > 0 && <span className="tabular-nums">{count}</span>}
              </button>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

function GiveRecognitionDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const { me } = useAuth();
  const { nodes } = useDirectory();
  const meta = useRecognitionMeta();
  const m = useRecognitionMutations();

  const people = Object.values(nodes).filter((p) => p.id !== me?.id);
  const values = meta.data?.values ?? [];
  const visibilities = meta.data?.visibilities ?? [];

  const [recipient, setRecipient] = React.useState("");
  const [value, setValue] = React.useState("");
  const [message, setMessage] = React.useState("");
  const [visibility, setVisibility] = React.useState<RecognitionVisibility>("TEAM");
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (open) {
      setRecipient("");
      setValue("");
      setMessage("");
      setVisibility("TEAM");
      setError(null);
    }
  }, [open]);

  const ok = Boolean(recipient && value && message.trim());

  async function submit() {
    setError(null);
    try {
      await m.give.mutateAsync({ recipient, value, message: message.trim(), visibility });
      notifySuccess("Recognition shared");
      onOpenChange(false);
    } catch (err) {
      const detail = (err as { message?: string })?.message;
      setError(detail || "Couldn't share that recognition.");
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Give recognition</DialogTitle>
          <DialogDescription>
            Recognise a teammate for living a company value. You choose who can see it.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {error && (
            <p className="rounded-md bg-danger-subtle px-3 py-2 text-sm text-danger">{error}</p>
          )}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Recipient" required>
              <Select value={recipient} onValueChange={setRecipient}>
                <SelectTrigger><SelectValue placeholder="Select a teammate…" /></SelectTrigger>
                <SelectContent>
                  {people.map((p) => (
                    <SelectItem key={p.id} value={p.id}>{p.display}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Company value" required>
              <Select value={value} onValueChange={setValue}>
                <SelectTrigger><SelectValue placeholder="Pick a value…" /></SelectTrigger>
                <SelectContent>
                  {values.map((v) => (
                    <SelectItem key={v} value={v}>{v}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          </div>
          <Field label="Message" required>
            <Textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="What did they do, and why did it matter?"
              className="min-h-20"
            />
          </Field>
          <Field label="Who can see this" hint="Private is just the two of you.">
            <Select value={visibility} onValueChange={(v) => setVisibility(v as RecognitionVisibility)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {visibilities.map((v) => (
                  <SelectItem key={v.value} value={v.value}>{v.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} loading={m.give.isPending} disabled={!ok}>
            Share recognition
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
