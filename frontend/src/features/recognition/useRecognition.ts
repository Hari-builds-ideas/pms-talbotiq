import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { recognitionApi } from "@/lib/api/endpoints";
import type { RecognitionVisibility } from "@/lib/types";

/** The viewer's visibility-filtered feed (server enforces who sees what). */
export function useRecognitionFeed() {
  return useQuery({ queryKey: ["recognition", "feed"], queryFn: recognitionApi.feed });
}

/** Form options (company values, reaction palette, visibility choices). Cached. */
export function useRecognitionMeta() {
  return useQuery({
    queryKey: ["recognition", "meta"],
    queryFn: recognitionApi.meta,
    staleTime: 5 * 60_000,
  });
}

export interface GiveRecognitionInput {
  recipient: string;
  value: string;
  message: string;
  visibility: RecognitionVisibility;
  badge?: string;
}

export function useRecognitionMutations() {
  const qc = useQueryClient();
  const refresh = () => void qc.invalidateQueries({ queryKey: ["recognition", "feed"] });
  return {
    give: useMutation({ mutationFn: (b: GiveRecognitionInput) => recognitionApi.give(b), onSuccess: refresh }),
    react: useMutation({
      mutationFn: (v: { id: string; emoji: string }) => recognitionApi.react(v.id, v.emoji),
      onSuccess: refresh,
    }),
    remove: useMutation({ mutationFn: (id: string) => recognitionApi.remove(id), onSuccess: refresh }),
  };
}
