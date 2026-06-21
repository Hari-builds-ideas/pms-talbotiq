import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { reviewsApi } from "@/lib/api/endpoints";
import type { PageParams } from "@/lib/api/endpoints";

export function useReviews(params: PageParams & { cycle?: string }) {
  return useQuery({
    queryKey: ["reviews", "list", params],
    queryFn: () => reviewsApi.list(params),
  });
}

export function useReview(id: string | undefined) {
  return useQuery({
    queryKey: ["reviews", "detail", id],
    queryFn: () => reviewsApi.detail(id as string),
    enabled: Boolean(id),
    // Poll while the AI is drafting (transient state) until it settles.
    refetchInterval: (query) =>
      query.state.data?.state === "AI_DRAFTING" ? 1500 : false,
  });
}

export function useReviewTimeline(id: string | undefined) {
  return useQuery({
    queryKey: ["reviews", "timeline", id],
    queryFn: () => reviewsApi.timeline(id as string),
    enabled: Boolean(id),
  });
}

export function useReviewAssessments(id: string | undefined) {
  return useQuery({
    queryKey: ["reviews", "assessments", id],
    queryFn: () => reviewsApi.assessments(id as string),
    enabled: Boolean(id),
  });
}

export function useReviewComments(id: string | undefined) {
  return useQuery({
    queryKey: ["reviews", "comments", id],
    queryFn: () => reviewsApi.comments(id as string),
    enabled: Boolean(id),
  });
}

export function useReviewCommentMutations(reviewId: string) {
  const qc = useQueryClient();
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["reviews", "comments", reviewId] });
  };
  return {
    create: useMutation({
      mutationFn: (v: { body: string; section?: string | null; parent?: string | null }) =>
        reviewsApi.createComment(reviewId, v),
      onSuccess: refresh,
    }),
    edit: useMutation({
      mutationFn: (v: { id: string; body: string }) =>
        reviewsApi.editComment(reviewId, v.id, v.body),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: string) => reviewsApi.deleteComment(reviewId, id),
      onSuccess: refresh,
    }),
  };
}

export function useReviewTransitions(id: string) {
  const qc = useQueryClient();
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["reviews", "detail", id] });
    void qc.invalidateQueries({ queryKey: ["reviews", "timeline", id] });
    void qc.invalidateQueries({ queryKey: ["reviews", "list"] });
  };
  return {
    startEdit: useMutation({ mutationFn: () => reviewsApi.startEdit(id), onSuccess: refresh }),
    saveDraft: useMutation({ mutationFn: (body: string) => reviewsApi.saveDraft(id, body), onSuccess: refresh }),
    submit: useMutation({ mutationFn: (body: string) => reviewsApi.submit(id, body), onSuccess: refresh }),
    approve: useMutation({ mutationFn: () => reviewsApi.approve(id), onSuccess: refresh }),
    reject: useMutation({ mutationFn: (reason: string) => reviewsApi.reject(id, reason), onSuccess: refresh }),
    finalize: useMutation({ mutationFn: () => reviewsApi.finalize(id), onSuccess: refresh }),
    requestAiDraft: useMutation({ mutationFn: () => reviewsApi.requestAiDraft(id), onSuccess: refresh }),
  };
}
