import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { careerApi } from "@/lib/api/endpoints";
import type { RoadmapProgressStatus } from "@/lib/types";

// ── reads ──────────────────────────────────────────────────────────────────
/** The caller's OWN roadmaps (every role — own scope). */
export function useMyRoadmaps() {
  return useQuery({ queryKey: ["career", "roadmap", "mine"], queryFn: careerApi.roadmap });
}

/** Roadmaps in the actor's scope, optionally for one employee (Manager TEAM,
 * HRBP/Admin TENANT). An out-of-scope employee 404s in the service. */
export function useScopedRoadmaps(employee?: string) {
  return useQuery({
    queryKey: ["career", "roadmaps", employee ?? "all"],
    queryFn: () => careerApi.roadmaps({ employee, page_size: 100 }),
  });
}

/** The live deterministic skill gap for a roadmap's employee (no LLM). */
export function useSkillGap(roadmapId: string | null) {
  return useQuery({
    queryKey: ["career", "skill-gap", roadmapId],
    queryFn: () => careerApi.skillGap(roadmapId as string),
    enabled: Boolean(roadmapId),
  });
}

/** Per-tier progress for a roadmap. */
export function useRoadmapProgress(roadmapId: string | null) {
  return useQuery({
    queryKey: ["career", "progress", roadmapId],
    queryFn: () => careerApi.progress(roadmapId as string),
    enabled: Boolean(roadmapId),
  });
}

// ── mutations ────────────────────────────────────────────────────────────────
export function useCareerMutations() {
  const qc = useQueryClient();
  const invalidate = () => void qc.invalidateQueries({ queryKey: ["career"] });
  return {
    selectTarget: useMutation({
      mutationFn: (v: { employee?: string; target_jd?: string; target_position?: string }) =>
        careerApi.selectTarget(v),
      onSuccess: invalidate,
    }),
    regenerate: useMutation({
      mutationFn: (id: string) => careerApi.regenerate(id),
      onSuccess: invalidate,
    }),
    enrich: useMutation({
      mutationFn: (id: string) => careerApi.enrich(id),
      onSuccess: invalidate,
    }),
    setProgress: useMutation({
      mutationFn: (v: { id: string; tier_index: number; status: RoadmapProgressStatus }) =>
        careerApi.setProgress(v.id, { tier_index: v.tier_index, status: v.status }),
      onSuccess: invalidate,
    }),
  };
}
