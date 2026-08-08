import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HowToUse, starterPrompts } from "./HowToUse";

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

/**
 * These render the component, which the first version of this file did not.
 * `starterPrompts` is a pure function and passed happily while the affordance beside
 * "New chat" was never verified to appear at all — the gap that let a missing button
 * reach the user.
 */
describe("How to use", () => {
  it("puts a trigger in the header", () => {
    render(<HowToUse canSeeTeam />);
    expect(screen.getByRole("button", { name: /how to use/i })).toBeInTheDocument();
  });

  it("opens onto both what it can and cannot do", async () => {
    render(<HowToUse canSeeTeam />);
    await userEvent.click(screen.getByRole("button", { name: /how to use/i }));

    expect(await screen.findByText(/what i can do/i)).toBeInTheDocument();
    expect(screen.getByText(/what i can.?t do/i)).toBeInTheDocument();
    // The two limits users hit first.
    expect(screen.getByText(/you approve every action first/i)).toBeInTheDocument();
    expect(screen.getByText(/outside your access/i)).toBeInTheDocument();
  });

  it("tells an employee they can only see their own data", async () => {
    render(<HowToUse canSeeTeam={false} />);
    await userEvent.click(screen.getByRole("button", { name: /how to use/i }));

    expect(await screen.findByText(/only your own/i)).toBeInTheDocument();
    expect(screen.queryByText(/rank or compare your team/i)).not.toBeInTheDocument();
  });
});
