import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { approvalsApi } from "@/lib/api/endpoints";
import type { ApprovalWorkflow } from "@/lib/types";

const INBOX_KEY = ["approvals", "inbox"];
const WORKFLOWS_KEY = ["approvals", "workflows"];

export function useInbox() {
  return useQuery({ queryKey: INBOX_KEY, queryFn: approvalsApi.inbox });
}

export function useWorkflows() {
  return useQuery({ queryKey: WORKFLOWS_KEY, queryFn: approvalsApi.workflows });
}

export function useRoute(id: string | null) {
  return useQuery({
    queryKey: ["approvals", "route", id],
    queryFn: () => approvalsApi.route(id as string),
    enabled: Boolean(id),
  });
}

export function useStepMutations(routeId: string | null) {
  const qc = useQueryClient();
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: INBOX_KEY });
    if (routeId) void qc.invalidateQueries({ queryKey: ["approvals", "route", routeId] });
  };
  return {
    approve: useMutation({
      mutationFn: (v: { id: string; comment?: string }) =>
        approvalsApi.approveStep(v.id, v.comment),
      onSuccess: invalidate,
    }),
    reject: useMutation({
      mutationFn: (v: { id: string; comment: string }) =>
        approvalsApi.rejectStep(v.id, v.comment),
      onSuccess: invalidate,
    }),
  };
}

export function useWorkflowMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: WORKFLOWS_KEY });
  return {
    create: useMutation({
      mutationFn: (body: Partial<ApprovalWorkflow>) => approvalsApi.createWorkflow(body),
      onSuccess: invalidate,
    }),
    activate: useMutation({
      mutationFn: (id: string) => approvalsApi.activateWorkflow(id),
      onSuccess: invalidate,
    }),
    deactivate: useMutation({
      mutationFn: (id: string) => approvalsApi.deactivateWorkflow(id),
      onSuccess: invalidate,
    }),
  };
}
