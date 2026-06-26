/**
 * BUG 4 regression: the JD detail screen crashed ("This screen hit an unexpected
 * error") when a JD body was partial/empty. The backend stores `body` as a JSONField
 * defaulting to `{}` (manual draft, or before any AI/author body), so at runtime
 * `body.responsibilities` could be undefined while the type says string[] — and the
 * editor called `.join("\n")` on it. normalizeBody coerces any partial/null body to a
 * complete JdBody so `.join`/`.map` are always safe. These assert that contract.
 */
import { describe, it, expect } from "vitest";
import { normalizeBody } from "./JdDetailPage";

describe("normalizeBody (JD detail crash guard)", () => {
  it("coerces an empty {} body (manual draft) to safe defaults — no missing arrays", () => {
    const b = normalizeBody({} as never);
    expect(b.summary).toBe("");
    expect(b.responsibilities).toEqual([]);
    expect(b.must_haves).toEqual([]);
    expect(b.nice_to_haves).toEqual([]);
    // The exact operations the editor performs must not throw.
    expect(() => b.responsibilities.join("\n")).not.toThrow();
  });

  it("handles null / undefined bodies", () => {
    for (const input of [null, undefined]) {
      const b = normalizeBody(input);
      expect(b.responsibilities).toEqual([]);
      expect(() => b.must_haves.join("\n")).not.toThrow();
    }
  });

  it("fills in only the missing fields and preserves present ones", () => {
    const b = normalizeBody({ summary: "Owns the data platform", responsibilities: ["Build dbt models"] } as never);
    expect(b.summary).toBe("Owns the data platform");
    expect(b.responsibilities).toEqual(["Build dbt models"]);
    expect(b.must_haves).toEqual([]); // missing → safe default
    expect(b.nice_to_haves).toEqual([]);
  });

  it("passes a complete body through unchanged", () => {
    const full = { summary: "s", responsibilities: ["r"], must_haves: ["m"], nice_to_haves: ["n"] };
    expect(normalizeBody(full)).toEqual(full);
  });
});
