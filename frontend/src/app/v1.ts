/**
 * v1 product-scope switches — the single place that HIDES enterprise features too
 * complex for a first SME release. The code, routes, endpoints and components all stay
 * intact (nothing is deleted); these flags just remove them from the v1 UI so v2 can
 * flip them back on. This is deliberately NOT the billing `hasFeature()` lever (that's
 * per-tenant AI-pack entitlement) — this is a static, product-wide scope cut.
 *
 * To RE-ENABLE a feature for v2: remove its path from V1_HIDDEN_PATHS (nav + routes +
 * command palette pick it back up automatically), and set V1_HIDE_CALIBRATION = false
 * to restore the Analytics calibration / nine-box tab. See docs/handoff/V1_VS_V2.md.
 */

/** Nav destinations hidden from the v1 UI (deferred to v2; code retained). */
export const V1_HIDDEN_PATHS: ReadonlySet<string> = new Set<string>([
  "/career", // Career roadmaps — deferred to v2
  "/succession", // Succession + nine-box + critical roles — enterprise, deferred to v2
  "/admin/tenant", // Raw-JSON tenant-config editor — too technical for v1 admins
]);

/** True if a nav/route destination is hidden in v1 (prefix-aware). */
export function isHiddenInV1(to: string): boolean {
  if (V1_HIDDEN_PATHS.has(to)) return true;
  for (const p of V1_HIDDEN_PATHS) {
    if (to.startsWith(p + "/")) return true;
  }
  return false;
}

/** Hide the Analytics calibration / nine-box grid tab in v1 (kept in code for v2). */
export const V1_HIDE_CALIBRATION = true;
