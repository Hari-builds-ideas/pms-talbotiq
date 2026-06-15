import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { orgApi } from "@/lib/api/endpoints";
import type { PageParams } from "@/lib/api/endpoints";

export function useOrgTree() {
  return useQuery({ queryKey: ["org", "tree"], queryFn: orgApi.tree });
}

export function usePerson(id: string | null) {
  return useQuery({
    queryKey: ["org", "person", id],
    queryFn: () => orgApi.person(id as string),
    enabled: Boolean(id),
  });
}

export function usePositions(params: PageParams) {
  return useQuery({
    queryKey: ["org", "positions", params],
    queryFn: () => orgApi.positions(params),
  });
}

export function useVacancies() {
  return useQuery({ queryKey: ["org", "vacancies"], queryFn: orgApi.vacancies });
}

export function useOrgMutations() {
  const qc = useQueryClient();
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["org"] });
  };
  return {
    createPosition: useMutation({
      mutationFn: (b: { title: string; reports_to: string | null; department: string }) =>
        orgApi.createPosition(b),
      onSuccess: invalidate,
    }),
    fill: useMutation({
      mutationFn: (v: { id: string; filled_by: string }) => orgApi.fillPosition(v.id, v.filled_by),
      onSuccess: invalidate,
    }),
    close: useMutation({
      mutationFn: (id: string) => orgApi.closePosition(id),
      onSuccess: invalidate,
    }),
    linkJd: useMutation({
      mutationFn: (v: { id: string; jd: string }) => orgApi.linkJd(v.id, v.jd),
      onSuccess: invalidate,
    }),
    unlinkJd: useMutation({
      mutationFn: (id: string) => orgApi.unlinkJd(id),
      onSuccess: invalidate,
    }),
    reassign: useMutation({
      mutationFn: (v: { employee: string; manager: string | null }) =>
        orgApi.reassign(v.employee, v.manager),
      onSuccess: invalidate,
    }),
  };
}
