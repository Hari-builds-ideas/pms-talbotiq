import { describe, expect, it } from "vitest";
import { sumWeights, weightsSumTo100, WEIGHT_EPSILON } from "./weights";

describe("weights", () => {
  it("sums string and numeric weights, tolerating blanks", () => {
    expect(sumWeights([{ weight: "40" }, { weight: "60" }])).toBe(100);
    expect(sumWeights([{ weight: 25 }, { weight: "" }, { weight: "25.5" }])).toBeCloseTo(50.5);
    expect(sumWeights([])).toBe(0);
  });

  it("accepts an exact 100 and rejects anything outside the epsilon", () => {
    expect(weightsSumTo100([{ weight: "100" }])).toBe(true);
    expect(weightsSumTo100([{ weight: "33.33" }, { weight: "33.33" }, { weight: "33.34" }])).toBe(true);
    expect(weightsSumTo100([{ weight: "50" }, { weight: "49" }])).toBe(false); // 99
    expect(weightsSumTo100([{ weight: "60" }, { weight: "60" }])).toBe(false); // 120
    expect(weightsSumTo100([])).toBe(false); // 0 ≠ 100
  });

  it("treats a near-100 within epsilon as valid (rounding tolerance)", () => {
    expect(weightsSumTo100([{ weight: String(100 - WEIGHT_EPSILON / 2) }])).toBe(true);
    expect(weightsSumTo100([{ weight: "99.99" }])).toBe(false); // 0.01 > epsilon
  });
});
