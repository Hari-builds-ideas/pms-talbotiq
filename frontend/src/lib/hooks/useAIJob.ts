import { useQuery } from "@tanstack/react-query";

import { aiJobsApi } from "@/lib/api/endpoints";
import type { AIJob, AIJobStatus } from "@/lib/types";

const TERMINAL: AIJobStatus[] = ["SUCCEEDED", "DEGRADED", "FAILED"];

export function isTerminal(status?: AIJobStatus | null): boolean {
  return !!status && TERMINAL.includes(status);
}

/**
 * Poll an async AI job until it reaches a terminal state. Pass a falsy id to
 * disable (no run in flight). While QUEUED/RUNNING it polls every 1.5s; once
 * SUCCEEDED/DEGRADED/FAILED it stops. Callers react to the terminal status:
 * SUCCEEDED → refetch the artifact; DEGRADED/FAILED → show the calm banner.
 */
export function useAIJob(jobId: string | null | undefined) {
  return useQuery({
    queryKey: ["ai", "job", jobId],
    queryFn: () => aiJobsApi.get(jobId as string),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const job = query.state.data as AIJob | undefined;
      return job && isTerminal(job.status) ? false : 1500;
    },
  });
}
