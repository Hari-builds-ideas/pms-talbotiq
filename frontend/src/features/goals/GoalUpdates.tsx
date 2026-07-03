import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquarePlus } from "lucide-react";
import { goalsApi } from "@/lib/api/endpoints";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { notifyError, notifySuccess } from "@/lib/toast";

/**
 * The goal "Updates" timeline (AGENT_UX_V3 Part 2.3) — short progress notes under a
 * goal card. The owner (and a manager in scope) can add one; the write goes through
 * the audited `/api/goals/:id/updates` endpoint. Reads real data only; honest empty.
 */
export function GoalUpdates({ goalId, canAdd }: { goalId: string; canAdd?: boolean }) {
  const qc = useQueryClient();
  const [text, setText] = React.useState("");
  const q = useQuery({
    queryKey: ["goals", "updates", goalId],
    queryFn: () => goalsApi.goalUpdates(goalId),
  });
  const add = useMutation({
    mutationFn: (body: string) => goalsApi.addGoalUpdate(goalId, body),
    onSuccess: () => {
      setText("");
      notifySuccess("Update added");
      void qc.invalidateQueries({ queryKey: ["goals", "updates", goalId] });
    },
    onError: notifyError,
  });
  const updates = q.data ?? [];

  return (
    <div className="space-y-1.5 border-t border-border pt-2">
      <p className="text-2xs font-semibold uppercase tracking-wide text-muted-foreground">Updates</p>
      {updates.length === 0 ? (
        <p className="text-2xs italic text-muted-foreground">No updates yet.</p>
      ) : (
        <ul className="space-y-1">
          {updates.map((u) => (
            <li key={u.id} className="text-2xs text-foreground">
              {u.text} <span className="text-muted-foreground">— {u.author_name ?? "Someone"}</span>
            </li>
          ))}
        </ul>
      )}
      {canAdd && (
        <div className="flex items-center gap-1.5">
          <Input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Add an update…"
            className="h-7 text-xs"
            aria-label="Add a goal update"
          />
          <Button
            size="sm"
            variant="ghost"
            disabled={!text.trim()}
            loading={add.isPending}
            onClick={() => add.mutate(text.trim())}
          >
            <MessageSquarePlus className="h-3.5 w-3.5" /> Add
          </Button>
        </div>
      )}
    </div>
  );
}
