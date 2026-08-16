import { useQuery } from "@tanstack/react-query";
import { authApi, type PublicConfig } from "@/lib/api/endpoints";

/**
 * The pre-login facts the SPA needs from the server (C7): is self-serve signup
 * open, who to contact, which SSO buttons to show.
 *
 * Read from the API rather than `import.meta.env` so an operator flipping
 * `SIGNUP_MODE` gets the change on the next page load instead of needing a
 * frontend rebuild and redeploy.
 *
 * Cached for the session and never retried into a loop: if this endpoint is
 * unreachable the login page must still render, so callers fall back to the
 * closed/safe assumption rather than blocking on it.
 */
export function usePublicConfig() {
  const q = useQuery<PublicConfig>({
    queryKey: ["auth", "public-config"],
    queryFn: authApi.publicConfig,
    staleTime: 5 * 60_000,
    retry: false,
  });

  return {
    ...q,
    /** Default CLOSED while loading or on error — advertising a signup form that
     *  will be refused is worse than briefly not advertising one that works. */
    signupOpen: q.data?.signup_open ?? false,
    supportEmail: q.data?.support_email ?? null,
  };
}
