import { describe, expect, it } from "vitest";
import { bucketByEffectiveBox } from "./nineBox";
import type { NineBoxPlacement } from "@/lib/types";

const p = (id: string, box: number, override: number | null = null): NineBoxPlacement => ({
  id,
  employee: `e-${id}`,
  employee_name: id,
  cycle: "c1",
  performance_band: "MEDIUM",
  potential_band: "MEDIUM",
  box,
  override_box: override,
  override_at: null,
  effective_box: override ?? box,
  is_overridden: override !== null,
});

describe("bucketByEffectiveBox", () => {
  it("buckets by computed box when there's no override", () => {
    const map = bucketByEffectiveBox([p("a", 5), p("b", 5), p("c", 9)]);
    expect(map.get(5)!.map((x) => x.id)).toEqual(["a", "b"]);
    expect(map.get(9)!.map((x) => x.id)).toEqual(["c"]);
  });

  it("places an overridden person in the override cell, not the computed one", () => {
    const map = bucketByEffectiveBox([p("a", 1, 9)]); // computed 1, dragged to 9
    expect(map.get(9)!.map((x) => x.id)).toEqual(["a"]);
    expect(map.get(1)).toBeUndefined();
  });

  it("returns an empty map for no placements", () => {
    expect(bucketByEffectiveBox([]).size).toBe(0);
  });
});
