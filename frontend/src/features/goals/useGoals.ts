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

export function useGoalMutations(cycle: string | undefined) {
  const qc = useQueryClient();
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["goals", "list", cycle] });
    void qc.invalidateQueries({ queryKey: ["cycles", "scores", cycle] });
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
