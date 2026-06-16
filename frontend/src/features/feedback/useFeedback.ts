import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { feedbackApi } from "@/lib/api/endpoints";

// ── giver surface ────────────────────────────────────────────────────────────
export function useMyRequests() {
  return useQuery({ queryKey: ["feedback", "requests", "mine"], queryFn: feedbackApi.requestsMine });
}

// ── manager surface ──────────────────────────────────────────────────────────
export function useCycles() {
  return useQuery({ queryKey: ["feedback", "cycles"], queryFn: () => feedbackApi.cycles({ page_size: 100 }) });
}

export function useInvitations(cycleId: string | null) {
  return useQuery({
    queryKey: ["feedback", "invitations", cycleId],
    queryFn: () => feedbackApi.invitations(cycleId as string),
    enabled: Boolean(cycleId),
  });
}

export function useAnonymized(cycleId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ["feedback", "anonymized", cycleId],
    queryFn: () => feedbackApi.anonymized(cycleId as string),
    enabled: Boolean(cycleId) && enabled,
    retry: false,
  });
}

// ── HRBP surface ─────────────────────────────────────────────────────────────
export function useReviewQueue() {
  return useQuery({ queryKey: ["feedback", "summaries", "review"], queryFn: () => feedbackApi.summariesReview() });
}

// ── subject surface ──────────────────────────────────────────────────────────
export function useMySummary(cycleId: string | null) {
  return useQuery({
    queryKey: ["feedback", "summary", cycleId],
    queryFn: () => feedbackApi.summary(cycleId as string),
    enabled: Boolean(cycleId),
    retry: false, // 403 SUMMARY_NOT_RELEASED / 404 are expected states, not transient
  });
}

export function useFeedbackMutations() {
  const qc = useQueryClient();
  const invalidate = () => void qc.invalidateQueries({ queryKey: ["feedback"] });
  return {
    give: useMutation({
      mutationFn: (v: { cycleId: string; body: string; marked_sensitive: boolean }) =>
        feedbackApi.give(v.cycleId, { body: v.body, marked_sensitive: v.marked_sensitive }),
      onSuccess: invalidate,
    }),
    decline: useMutation({
      mutationFn: (id: string) => feedbackApi.declineRequest(id),
      onSuccess: invalidate,
    }),
    createCycle: useMutation({
      mutationFn: (v: { subject: string; min_volume?: number }) => feedbackApi.createCycle(v),
      onSuccess: invalidate,
    }),
    openCycle: useMutation({
      mutationFn: (id: string) => feedbackApi.openCycle(id),
      onSuccess: invalidate,
    }),
    invite: useMutation({
      mutationFn: (v: { cycleId: string; giver: string; relationship: string }) =>
        feedbackApi.invite(v.cycleId, { giver: v.giver, relationship: v.relationship }),
      onSuccess: invalidate,
    }),
    closeCycle: useMutation({
      mutationFn: (id: string) => feedbackApi.closeCycle(id),
      onSuccess: invalidate,
    }),
    summarize: useMutation({
      mutationFn: (id: string) => feedbackApi.summarize(id),
      onSuccess: invalidate,
    }),
    approveSummary: useMutation({
      mutationFn: (id: string) => feedbackApi.approveSummary(id),
      onSuccess: invalidate,
    }),
  };
}
