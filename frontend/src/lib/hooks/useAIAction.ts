import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";

import type { AIJob } from "@/lib/types";
import { isTerminal, useAIJob } from "./useAIJob";

interface Options {
  /** Called once when the job reaches SUCCEEDED — re-fetch the artifact here. */
  onSucceeded?: () => void;
  /** Called once when the job reaches any terminal state. */
  onSettled?: () => void;
}

/**
 * Drive one async AI seam from a component: fire the action (which returns an
 * AIJob), then poll it to a terminal state. Returns `job` for rendering
 * `<AIJobBanner>`, `isWorking` for disabling the trigger, and `start` to
 * (re-)fire. Reacts to SUCCEEDED/terminal via the (stable-by-ref) callbacks.
 */
export function useAIAction(fire: () => Promise<AIJob>, opts?: Options) {
  const [jobId, setJobId] = useState<string | null>(null);
  const optsRef = useRef(opts);
  optsRef.current = opts;

  const mutation = useMutation({
    mutationFn: fire,
    onSuccess: (job) => setJobId(job.id),
  });

  const poll = useAIJob(jobId);
  const job = poll.data ?? null;

  useEffect(() => {
    if (!job || !isTerminal(job.status)) return;
    if (job.status === "SUCCEEDED") optsRef.current?.onSucceeded?.();
    optsRef.current?.onSettled?.();
  }, [job]);

  return {
    start: () => mutation.mutate(),
    job,
    isStarting: mutation.isPending,
    isWorking: mutation.isPending || (!!job && !isTerminal(job.status)),
    startError: mutation.error,
    reset: () => setJobId(null),
  };
}
