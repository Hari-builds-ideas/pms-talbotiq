import { useQuery } from "@tanstack/react-query";
import { cyclesApi } from "@/lib/api/endpoints";

/** Performance cycles (cached). Used by reviews, analytics and succession. */
export function useCycles() {
  const query = useQuery({
    queryKey: ["cycles"],
    queryFn: cyclesApi.list,
    staleTime: 5 * 60_000,
  });
  const cycles = query.data ?? [];
  const active = cycles.find((c) => c.status === "ACTIVE") ?? cycles[0];
  function nameOf(id?: string | null) {
    return cycles.find((c) => c.id === id)?.name ?? id ?? "—";
  }
  return { ...query, cycles, active, nameOf };
}
