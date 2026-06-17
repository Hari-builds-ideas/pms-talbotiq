import { useQuery } from "@tanstack/react-query";
import { cyclesApi } from "@/lib/api/endpoints";
import { looksLikeUuid } from "@/lib/format";

/** Performance cycles (cached). Used by reviews, analytics and succession.
 * The cycle list is Manager+; for callers who can't read it, prefer a
 * server-resolved `*_cycle_name` and never render the raw uuid. */
export function useCycles() {
  const query = useQuery({
    queryKey: ["cycles"],
    queryFn: cyclesApi.list,
    staleTime: 5 * 60_000,
  });
  const cycles = query.data ?? [];
  const active = cycles.find((c) => c.status === "ACTIVE") ?? cycles[0];
  function nameOf(id?: string | null) {
    if (!id) return "—";
    const found = cycles.find((c) => c.id === id)?.name;
    if (found) return found;
    return looksLikeUuid(id) ? "Cycle" : id;
  }
  return { ...query, cycles, active, nameOf };
}
