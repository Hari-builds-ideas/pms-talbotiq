import { QueryClient } from "@tanstack/react-query";
import { mapApiError } from "./errors";

/**
 * Shared React Query client. Retries are conservative — we never retry a 4xx
 * (those are deterministic: forbidden, not-found, conflict, domain). 401 is
 * handled by the axios refresh interceptor, not by retrying here.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        const mapped = mapApiError(error);
        if (mapped.status && mapped.status >= 400 && mapped.status < 500) {
          return false;
        }
        return failureCount < 2;
      },
    },
    mutations: {
      retry: false,
    },
  },
});
