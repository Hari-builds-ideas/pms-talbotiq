import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cyclesApi, goalsApi } from "@/lib/api/endpoints";
import type { Goal } from "@/lib/types";

export function useGoals(cycle: string | undefined) {
  return useQuery({
    queryKey: ["goals", "list", cycle ?? "all"],
    queryFn: () => goalsApi.list(cycle ? { cycle, page_size: 200 } : { page_size: 200 }),
  });
}

export function useCycleScores(cycle: string | undefined) {
  return useQuery({
    queryKey: ["cycles", "scores", cycle],
    queryFn: () => cyclesApi.scores(cycle as string),
    enabled: Boolean(cycle),
  });
}

export function useGoalMutations(_cycle?: string | undefined) {
  const qc = useQueryClient();
  // Invalidate by the stable PREFIX, not a cycle-specific key. The list query key
  // normalizes the cycle to "all" when none is selected (`cycle ?? "all"`), so a
  // `["goals","list", cycle]` key with cycle===undefined never matched the cached
  // `["goals","list","all"]` query — approve/create/recompute showed a success
  // toast but the row never refetched. A prefix match covers every cached variant.
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["goals", "list"] });
    void qc.invalidateQueries({ queryKey: ["cycles", "scores"] });
  };
  return {
    create: useMutation({
      mutationFn: (body: Parameters<typeof goalsApi.create>[0]) => goalsApi.create(body),
      onSuccess: refresh,
    }),
    approve: useMutation({
      mutationFn: (id: string) => goalsApi.approve(id),
      onSuccess: refresh,
    }),
    recordActual: useMutation({
      mutationFn: (v: { kpiId: string; value: string }) => goalsApi.recordActual(v.kpiId, v.value),
      onSuccess: refresh,
    }),
    recompute: useMutation({
      mutationFn: (cycleId: string) => cyclesApi.recompute(cycleId),
      onSuccess: refresh,
    }),
  };
}

/** Sum of an employee's ACTIVE goal weights (the 100.00 invariant indicator). */
export function activeWeightTotal(goals: Goal[], employee: string): number {
  return goals
    .filter((g) => g.employee === employee && g.status === "ACTIVE")
    .reduce((s, g) => s + Number(g.weight), 0);
}
