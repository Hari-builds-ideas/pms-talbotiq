/**
 * Goal progress — the plain "% complete" a non-technical manager reads first, plus
 * the colored status derived from it. This is the v1 Goals headline (replacing the
 * T-score): the simplest pattern the leading tools use (Lattice / 15Five / Betterworks
 * — see docs/GOALS_RESEARCH.md).
 *
 * The math mirrors the backend scoring engine (`apps/goals/scoring/engine.py`) so the
 * number the manager sees matches what the server computes:
 *   - per-KPI attainment  = direction-aware ratio (actual/target, or target/actual for
 *     "lower is better"), clamped to [0, 1.5]; an unrecorded KPI contributes 0.
 *   - goal %              = Σ (kpi.weight/100 × attainment) × 100.
 *   - person overall %    = weight-blended over the person's started goals.
 * If NO KPI on a goal has a recorded actual, the goal is "Not started" (pct = null) —
 * we never show a misleading 0% for a goal simply awaiting its first measurement.
 */
import type { Goal, Kpi } from "@/lib/types";

export type ProgressStatus = "ON_TRACK" | "BEHIND" | "AT_RISK";

/** The plain words a manager reads — no jargon. */
export const PROGRESS_STATUS_LABEL: Record<ProgressStatus, string> = {
  ON_TRACK: "On track",
  BEHIND: "Behind",
  AT_RISK: "At risk",
};

/** Progress-bar fill color per status (design tokens). */
export const PROGRESS_BAR_CLASS: Record<ProgressStatus, string> = {
  ON_TRACK: "bg-success",
  BEHIND: "bg-warning",
  AT_RISK: "bg-danger",
};

/** Matching text color per status. */
export const PROGRESS_TEXT_CLASS: Record<ProgressStatus, string> = {
  ON_TRACK: "text-success",
  BEHIND: "text-warning",
  AT_RISK: "text-danger",
};

/**
 * Status from % complete. Simple pure-% thresholds (a non-expert grasps them
 * instantly): ≥70 On track, 40–69 Behind, <40 At risk. (Real tools often also factor
 * in how far through the cycle you are — a documented v2 refinement, see PROGRESS_V1.md.)
 */
export function progressStatus(pct: number): ProgressStatus {
  if (pct >= 70) return "ON_TRACK";
  if (pct >= 40) return "BEHIND";
  return "AT_RISK";
}

const CAP = 1.5; // attainment cap — mirrors ATTAINMENT_CAP in the engine.

/** Direction-aware attainment ratio in [0, 1.5]; null if no actual recorded yet. */
function kpiRatio(kpi: Pick<Kpi, "target_value" | "latest_actual" | "direction">): number | null {
  const raw = kpi.latest_actual;
  if (raw === null || raw === undefined || raw === "") return null;
  const actual = Number(raw);
  const target = Number(kpi.target_value);
  let ratio: number;
  if (kpi.direction === "DECREASING") {
    ratio = actual === 0 ? CAP : target / actual; // drove it to zero = best result
  } else {
    ratio = target ? actual / target : 0;
  }
  return Math.max(0, Math.min(CAP, ratio));
}

export interface GoalProgress {
  /** 0–150 (%), or null if the goal hasn't started (no KPI recorded yet). */
  pct: number | null;
  status: ProgressStatus | null;
  recorded: number;
  total: number;
}

/** A goal's overall % complete + status, from its KPIs' recorded actuals. */
export function goalProgress(goal: Pick<Goal, "kpis">): GoalProgress {
  const kpis = goal.kpis ?? [];
  let recorded = 0;
  let weighted = 0;
  for (const k of kpis) {
    const r = kpiRatio(k);
    if (r !== null) {
      recorded += 1;
      weighted += (Number(k.weight) / 100) * r;
    }
    // an unrecorded KPI contributes 0 to the weighted sum (engine-consistent)
  }
  if (recorded === 0) return { pct: null, status: null, recorded: 0, total: kpis.length };
  const pct = weighted * 100;
  return { pct, status: progressStatus(pct), recorded, total: kpis.length };
}

export interface PersonProgress {
  /** Weight-blended overall % across the person's started goals; null if none started. */
  pct: number | null;
  onTrack: number;
  started: number;
  total: number;
}

/** Roll a person's goals into the one-line summary ("3 of 4 on track — 68% overall"). */
export function personProgress(goals: Goal[]): PersonProgress {
  let onTrack = 0;
  let started = 0;
  let weightSum = 0;
  let weighted = 0;
  for (const g of goals) {
    const p = goalProgress(g);
    if (p.pct === null) continue;
    started += 1;
    if (p.status === "ON_TRACK") onTrack += 1;
    const w = Number(g.weight) || 0;
    weightSum += w;
    weighted += w * p.pct;
  }
  const pct = started === 0 ? null : weightSum > 0 ? weighted / weightSum : weighted / started;
  return { pct, onTrack, started, total: goals.length };
}
