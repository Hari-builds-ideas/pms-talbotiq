import { useQuery } from "@tanstack/react-query";
import { orgApi } from "@/lib/api/endpoints";
import type { OrgNode } from "@/lib/types";

/**
 * A lightweight people directory backed by the (cached) org tree. Lets any
 * screen resolve a user UUID to a display name without threading names through
 * every payload. Scope follows the org tree (own line / subtree / tenant), so
 * an out-of-scope id simply falls back to a short id.
 */
export function useDirectory() {
  const { data } = useQuery({
    queryKey: ["org", "tree"],
    queryFn: orgApi.tree,
    staleTime: 5 * 60_000,
  });

  const nodes = data?.nodes ?? {};

  function nameOf(id?: string | null): string {
    if (!id) return "—";
    const node: OrgNode | undefined = nodes[id];
    if (node) return node.display;
    // Out of scope / not loaded: never surface a raw uuid to a human. Callers
    // with a server-resolved label should prefer it (PersonName's `name` prop).
    return "Unknown";
  }

  function roleOf(id?: string | null): string | undefined {
    if (!id) return undefined;
    return nodes[id]?.role;
  }

  return { nameOf, roleOf, nodes };
}
