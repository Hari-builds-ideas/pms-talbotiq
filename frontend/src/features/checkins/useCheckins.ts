import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { checkinsApi } from "@/lib/api/endpoints";
import type { CheckInPriorityStatus } from "@/lib/types";

/** The caller's own check-ins (newest first). */
export function useMyCheckins() {
  return useQuery({ queryKey: ["checkins", "mine"], queryFn: checkinsApi.mine });
}

/** A manager's reporting-subtree check-ins (enabled only for managers+). */
export function useTeamCheckins(enabled: boolean) {
  return useQuery({ queryKey: ["checkins", "team"], queryFn: checkinsApi.team, enabled });
}

export interface SaveCheckInInput {
  week_of: string;
  mood: number;
  wins?: string;
  blockers?: string;
  learning?: string;
  priorities?: { text: string; status?: CheckInPriorityStatus }[];
}

export function useCheckinMutations() {
  const qc = useQueryClient();
  const refresh = () => void qc.invalidateQueries({ queryKey: ["checkins"] });
  return {
    save: useMutation({ mutationFn: (b: SaveCheckInInput) => checkinsApi.upsert(b), onSuccess: refresh }),
    respond: useMutation({
      mutationFn: (v: {
        id: string;
        body: { comment?: string; follow_up?: boolean; add_to_one_on_one?: boolean };
      }) => checkinsApi.respond(v.id, v.body),
      onSuccess: refresh,
    }),
  };
}

/** The Monday (ISO yyyy-mm-dd) of the week containing `d` — the check-in cadence key. */
export function mondayOf(d = new Date()): string {
  const x = new Date(d);
  const offset = (x.getDay() + 6) % 7; // 0 = Monday
  x.setDate(x.getDate() - offset);
  return x.toISOString().slice(0, 10);
}
