import { describe, expect, it } from "vitest";
import { goalProgress, personProgress, progressStatus } from "./goalProgress";
import type { Goal, Kpi } from "@/lib/types";

// Minimal KPI/Goal factories — only the fields goalProgress reads.
function kpi(p: Partial<Kpi>): Kpi {
  return {
    id: "k", name: "kpi", weight: "100", target_value: "100",
    direction: "INCREASING", unit: "", source: "MANUAL", latest_actual: null,
    ...p,
  } as Kpi;
}
function goal(kpis: Kpi[], weight = "100"): Goal {
  return { id: "g", employee: "e", weight, kpis } as Goal;
}

describe("progressStatus thresholds", () => {
  it("≥70 On track, 40–69 Behind, <40 At risk", () => {
    expect(progressStatus(70)).toBe("ON_TRACK");
    expect(progressStatus(100)).toBe("ON_TRACK");
    expect(progressStatus(69)).toBe("BEHIND");
    expect(progressStatus(40)).toBe("BEHIND");
    expect(progressStatus(39)).toBe("AT_RISK");
    expect(progressStatus(0)).toBe("AT_RISK");
  });
});

describe("goalProgress", () => {
  it("is Not started (null) when no KPI has a recorded actual", () => {
    const p = goalProgress(goal([kpi({ latest_actual: null }), kpi({ latest_actual: undefined })]));
    expect(p.pct).toBeNull();
    expect(p.status).toBeNull();
    expect(p.recorded).toBe(0);
    expect(p.total).toBe(2);
  });

  it("INCREASING: actual/target, weight-blended", () => {
    // one KPI, weight 100, target 100, actual 80 → 80%
    const p = goalProgress(goal([kpi({ weight: "100", target_value: "100", latest_actual: "80" })]));
    expect(Math.round(p.pct!)).toBe(80);
    expect(p.status).toBe("ON_TRACK");
  });

  it("DECREASING: target/actual, clamped to 150%", () => {
    // lower is better: target 10, actual 5 → ratio 2 → clamped 1.5 → 150%
    const p = goalProgress(goal([kpi({ direction: "DECREASING", target_value: "10", latest_actual: "5" })]));
    expect(Math.round(p.pct!)).toBe(150);
    expect(p.status).toBe("ON_TRACK");
  });

  it("an unrecorded KPI contributes 0 to the rollup (engine-consistent)", () => {
    // two KPIs weight 50 each; one at 100%, one unrecorded → 50%
    const p = goalProgress(
      goal([
        kpi({ weight: "50", target_value: "100", latest_actual: "100" }),
        kpi({ weight: "50", target_value: "100", latest_actual: null }),
      ]),
    );
    expect(Math.round(p.pct!)).toBe(50);
    expect(p.status).toBe("BEHIND");
    expect(p.recorded).toBe(1);
  });
});

describe("personProgress", () => {
  it("weight-blends started goals and counts on-track", () => {
    const g1 = goal([kpi({ target_value: "100", latest_actual: "100" })], "50"); // 100% on track
    const g2 = goal([kpi({ target_value: "100", latest_actual: "40" })], "50"); // 40% behind
    const p = personProgress([g1, g2]);
    expect(Math.round(p.pct!)).toBe(70); // (50*100 + 50*40)/100
    expect(p.onTrack).toBe(1);
    expect(p.started).toBe(2);
    expect(p.total).toBe(2);
  });

  it("is null overall when nothing is started", () => {
    const p = personProgress([goal([kpi({ latest_actual: null })])]);
    expect(p.pct).toBeNull();
    expect(p.started).toBe(0);
    expect(p.total).toBe(1);
  });
});
