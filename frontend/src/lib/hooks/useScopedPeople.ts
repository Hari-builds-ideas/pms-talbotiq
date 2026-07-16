import { useMemo } from "react";
import { useAuth } from "@/lib/auth/AuthContext";
import { useDirectory } from "@/lib/hooks/useDirectory";
import { subtreeIds } from "@/lib/org";
import type { OrgNode } from "@/lib/types";

/**
 * The people the caller may TARGET with scope-checked create/manage actions
 * (new review, new goal, new 360 cycle, analytics subject/head) — mirroring the
 * server's `actor_can_access` data-scope rule (apps/rbac/scope.py): HRBP/Admin =
 * TENANT (everyone), Manager = TEAM (self + reporting subtree), Employee = OWN.
 * The org tree also returns the caller's own line UPWARD (their director/HRBP),
 * whom they can SEE but not act on — offering those in a picker is exactly the
 * "click → 403 outside your access scope" wall this hook removes (FINAL D2).
 */
export function useScopedPeople(): OrgNode[] {
  const { nodes } = useDirectory();
  const { me, atLeast } = useAuth();
  return useMemo(() => {
    const all = Object.values(nodes);
    if (atLeast("HRBP")) return all; // TENANT scope
    if (!me) return [];
    const allowed = subtreeIds(me.id, nodes); // TEAM/OWN: self + subtree
    return all.filter((p) => allowed.has(p.id));
  }, [nodes, me, atLeast]);
}
