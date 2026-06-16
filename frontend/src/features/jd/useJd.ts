import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { jdApi } from "@/lib/api/endpoints";
import type { PageParams } from "@/lib/api/endpoints";
import type { JdBody } from "@/lib/types";

export function useJdList(params: PageParams) {
  return useQuery({ queryKey: ["jd", "list", params], queryFn: () => jdApi.list(params) });
}

export function useJd(id: string | undefined) {
  return useQuery({
    queryKey: ["jd", "detail", id],
    queryFn: () => jdApi.detail(id as string),
    enabled: Boolean(id),
  });
}

export function useJdVersions(id: string | undefined) {
  return useQuery({
    queryKey: ["jd", "versions", id],
    queryFn: () => jdApi.versions(id as string),
    enabled: Boolean(id),
  });
}

export function useJdRequests(params: PageParams) {
  return useQuery({ queryKey: ["jd", "requests", params], queryFn: () => jdApi.requests(params) });
}

export function useJdMutations(id?: string) {
  const qc = useQueryClient();
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["jd"] });
  };
  return {
    create: useMutation({
      mutationFn: (b: { title: string; level: string; department: string }) => jdApi.create(b),
      onSuccess: refresh,
    }),
    saveDraft: useMutation({
      mutationFn: (body: JdBody) => jdApi.saveDraft(id as string, body),
      onSuccess: refresh,
    }),
    submit: useMutation({ mutationFn: () => jdApi.submit(id as string), onSuccess: refresh }),
    approve: useMutation({ mutationFn: () => jdApi.approve(id as string), onSuccess: refresh }),
    revise: useMutation({ mutationFn: () => jdApi.revise(id as string), onSuccess: refresh }),
    archive: useMutation({ mutationFn: () => jdApi.archive(id as string), onSuccess: refresh }),
    saveInputs: useMutation({
      mutationFn: (inputs: Record<string, unknown>) => jdApi.saveInputs(id as string, inputs),
      onSuccess: refresh,
    }),
    generate: useMutation({ mutationFn: () => jdApi.generate(id as string, {}), onSuccess: refresh }),
  };
}

export function useJdRequestMutations() {
  const qc = useQueryClient();
  const refresh = () => void qc.invalidateQueries({ queryKey: ["jd", "requests"] });
  return {
    create: useMutation({
      mutationFn: (b: { title: string; level: string; notes: string }) => jdApi.createRequest(b),
      onSuccess: refresh,
    }),
    fulfil: useMutation({ mutationFn: (id: string) => jdApi.fulfilRequest(id), onSuccess: refresh }),
    decline: useMutation({ mutationFn: (id: string) => jdApi.declineRequest(id), onSuccess: refresh }),
  };
}
