import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { successionApi } from "@/lib/api/endpoints";
import type { PageParams } from "@/lib/api/endpoints";
import type { CriticalRole } from "@/lib/types";
import type { Readiness } from "@/lib/enums";

export function useSuccessionDashboard() {
  return useQuery({ queryKey: ["succession", "dashboard"], queryFn: successionApi.dashboard });
}

export function useCriticalRoles(params: PageParams) {
  return useQuery({
    queryKey: ["succession", "critical-roles", params],
    queryFn: () => successionApi.criticalRoles(params),
  });
}

export function useBench(roleId: string | null) {
  return useQuery({
    queryKey: ["succession", "bench", roleId],
    queryFn: () => successionApi.bench(roleId as string),
    enabled: Boolean(roleId),
  });
}

export function useNineBox(cycle?: string) {
  return useQuery({
    queryKey: ["succession", "nine-box", cycle],
    queryFn: () => successionApi.nineBox(cycle ? { cycle, page_size: 200 } : { page_size: 200 }),
  });
}

export function usePlan(id: string | null) {
  return useQuery({
    queryKey: ["succession", "plan", id],
    queryFn: () => successionApi.plan(id as string),
    enabled: Boolean(id),
  });
}

export function useSuccessionMutations() {
  const qc = useQueryClient();
  const invalidate = () => void qc.invalidateQueries({ queryKey: ["succession"] });
  return {
    createRole: useMutation({
      mutationFn: (b: Partial<CriticalRole>) => successionApi.createCriticalRole(b),
      onSuccess: invalidate,
    }),
    setKnowledgeRisk: useMutation({
      mutationFn: (v: { id: string; knowledge_risk: string; risk_notes?: string }) =>
        successionApi.setKnowledgeRisk(v.id, v.knowledge_risk, v.risk_notes),
      onSuccess: invalidate,
    }),
    archiveRole: useMutation({
      mutationFn: (id: string) => successionApi.archiveCriticalRole(id),
      onSuccess: invalidate,
    }),
    addBench: useMutation({
      mutationFn: (v: { roleId: string; candidate: string; notes?: string }) =>
        successionApi.addBench(v.roleId, { candidate: v.candidate, notes: v.notes }),
      onSuccess: invalidate,
    }),
    setReadiness: useMutation({
      mutationFn: (v: { benchId: string; readiness: Readiness }) =>
        successionApi.setReadiness(v.benchId, v.readiness),
      onSuccess: invalidate,
    }),
    generate: useMutation({
      mutationFn: (roleId: string) => successionApi.generate(roleId),
      onSuccess: invalidate,
    }),
    addActionItem: useMutation({
      mutationFn: (v: { id: string; text: string }) => successionApi.addActionItem(v.id, v.text),
      onSuccess: (data) => qc.setQueryData(["succession", "plan", data.id], data),
    }),
    publish: useMutation({
      mutationFn: (id: string) => successionApi.publishPlan(id),
      onSuccess: () => invalidate(),
    }),
    enrich: useMutation({
      mutationFn: (id: string) => successionApi.enrichPlan(id),
    }),
    assessNineBox: useMutation({
      mutationFn: (v: { employee: string; cycle: string; potential_band: string }) =>
        successionApi.assessNineBox(v),
      onSuccess: invalidate,
    }),
  };
}
