import { describe, expect, it } from "vitest";
import { starterPrompts } from "./HowToUse";

/**
 * The starter chips are the first thing a new user sees, so what they OFFER is a
 * promise about what the assistant can answer. Offering an employee "who's at risk on
 * my team?" would be promising something the scope rules will then refuse.
 */
describe("starter prompts", () => {
  it("offers a manager team questions", () => {
    const chips = starterPrompts(true);
    expect(chips[0]).toBe("What can you do?");
    expect(chips.some((c) => /my team|my reports/i.test(c))).toBe(true);
  });

  it("never offers an employee a question about other people", () => {
    const chips = starterPrompts(false);
    expect(chips[0]).toBe("What can you do?");
    expect(chips.some((c) => /my team|my reports|at risk on/i.test(c))).toBe(false);
    expect(chips.every((c) => /you|I|my (goals|cycle)/i.test(c))).toBe(true);
  });

  it("leads with the capability question for both roles", () => {
    // It is the cheapest possible orientation — answered from the role, no model call.
    expect(starterPrompts(true)[0]).toBe(starterPrompts(false)[0]);
  });
});
