import { QueryClient } from "@tanstack/react-query";

/** One query client for the app. Conservative retry so a 401/403/404 doesn't
 *  hammer; the shared client already handles 401→refresh→retry once. */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});
