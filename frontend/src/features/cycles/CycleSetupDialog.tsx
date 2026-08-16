import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { cyclesApi } from "@/lib/api/endpoints";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/Field";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

/**
 * Create the first performance cycle.
 *
 * This dialog exists because the product had a genuine dead end. Goals and
 * reviews both require an ACTIVE cycle — the "New review" button is disabled
 * without one — and nothing in the SPA ever created a cycle. The API endpoint
 * has been there the whole time (`POST /api/cycles/`, MANAGE_CYCLES); it simply
 * had no caller. So a brand-new tenant could invite everybody, set up reporting
 * lines, and then find that the two central modules stayed switched off with no
 * screen anywhere to switch them on.
 *
 * It is deliberately opinionated. An admin doing this for the first time does not
 * want a blank form asking for dates: it defaults to a sensible half-year window
 * containing today, so the only real decision is the name.
 */

/** The half-year (Jan–Jun or Jul–Dec) that contains `today`. */
export function defaultWindow(today = new Date()) {
  const year = today.getFullYear();
  const firstHalf = today.getMonth() < 6;
  const start = firstHalf ? `${year}-01-01` : `${year}-07-01`;
  const end = firstHalf ? `${year}-06-30` : `${year}-12-31`;
  const name = firstHalf ? `H1 ${year}` : `H2 ${year}`;
  return { start, end, name };
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (id: string) => void;
}

export function CycleSetupDialog({ open, onOpenChange, onCreated }: Props) {
  const initial = React.useMemo(() => defaultWindow(), []);
  const [name, setName] = React.useState(initial.name);
  const [start, setStart] = React.useState(initial.start);
  const [end, setEnd] = React.useState(initial.end);
  const [error, setError] = React.useState<string | null>(null);
  const queryClient = useQueryClient();

  const create = useMutation({
    // ACTIVE, not DRAFT. A cycle created here is the one the admin is trying to
    // start working in — leaving it DRAFT would leave every screen looking
    // exactly as broken as before, with no hint that a second step exists.
    mutationFn: () =>
      cyclesApi.create({ name, start_date: start, end_date: end, status: "ACTIVE" }),
    onSuccess: (cycle) => {
      queryClient.invalidateQueries({ queryKey: ["cycles"] });
      onOpenChange(false);
      onCreated?.(cycle.id);
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: Record<string, string[] | string> } })?.response
          ?.data;
      const first =
        detail && typeof detail === "object"
          ? Object.values(detail).flat()[0]
          : undefined;
      setError(typeof first === "string" ? first : "Could not create the cycle.");
    },
  });

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (end < start) {
      setError("The end date must be on or after the start date.");
      return;
    }
    create.mutate();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Start a performance cycle</DialogTitle>
            <DialogDescription>
              A cycle is the period goals and reviews belong to. Everything else
              in the product hangs off one, so this is the first thing to set up.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <Field label="Name" htmlFor="cycle-name">
              <Input
                id="cycle-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                maxLength={128}
              />
            </Field>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Starts" htmlFor="cycle-start">
                <Input
                  id="cycle-start"
                  type="date"
                  value={start}
                  onChange={(e) => setStart(e.target.value)}
                  required
                />
              </Field>
              <Field label="Ends" htmlFor="cycle-end">
                <Input
                  id="cycle-end"
                  type="date"
                  value={end}
                  onChange={(e) => setEnd(e.target.value)}
                  required
                />
              </Field>
            </div>
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Creating…" : "Start the cycle"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
