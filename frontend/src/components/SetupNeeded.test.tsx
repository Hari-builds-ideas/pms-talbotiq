import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { SetupNeeded } from "./SetupNeeded";
import { defaultWindow } from "@/features/cycles/CycleSetupDialog";

/**
 * The brand-new-tenant path (F1).
 *
 * A tenant on its first day has no people, no reporting lines and no performance
 * cycle. Goals and reviews both require a cycle, and what the pages did was show
 * "create a review to start the cycle" and then HIDE the button, because the code
 * already knew there was no cycle to create one in. Every empty state looked
 * correct; the admin was simply stuck, with no screen anywhere that created a
 * cycle.
 */

function renderIn(ui: React.ReactNode) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe("SetupNeeded", () => {
  it("names the missing prerequisite instead of describing the empty list", () => {
    renderIn(
      <SetupNeeded
        title="Reviews start with a cycle"
        needs={{ label: "a performance cycle", onFix: () => {} }}
      />,
    );
    expect(screen.getByText(/needs a performance cycle first/i)).toBeInTheDocument();
  });

  it("offers the fix in place, so the person stays on the page they wanted", async () => {
    const onFix = vi.fn();
    renderIn(
      <SetupNeeded
        title="Reviews start with a cycle"
        needs={{ label: "a performance cycle", onFix }}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /set up a performance cycle/i }));
    expect(onFix).toHaveBeenCalledOnce();
  });

  it("offers no button to someone who cannot fix it, and says who can", () => {
    renderIn(
      <SetupNeeded
        title="Reviews start with a cycle"
        needs={{ label: "a performance cycle", onFix: () => {}, canFix: false }}
      />,
    );
    // A link to a page that will 403 is worse than no link.
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText(/ask an admin/i)).toBeInTheDocument();
  });

  it("falls back to a link when the fix lives on another screen", () => {
    renderIn(
      <SetupNeeded title="No one to review" needs={{ label: "people", to: "/admin/users" }} />,
    );
    expect(screen.getByRole("link", { name: /set up people/i })).toHaveAttribute(
      "href",
      "/admin/users",
    );
  });
});

describe("the first cycle's default window", () => {
  /**
   * An admin doing this for the first time should not be asked to think about
   * dates. The dialog proposes the half-year containing today, so the only real
   * decision is the name.
   */
  it("proposes the first half of the year in January", () => {
    expect(defaultWindow(new Date("2026-01-15T00:00:00Z"))).toEqual({
      start: "2026-01-01",
      end: "2026-06-30",
      name: "H1 2026",
    });
  });

  it("proposes the second half in August", () => {
    expect(defaultWindow(new Date("2026-08-17T00:00:00Z"))).toEqual({
      start: "2026-07-01",
      end: "2026-12-31",
      name: "H2 2026",
    });
  });

  it("never proposes a window that ends before it starts", () => {
    for (const month of Array.from({ length: 12 }, (_, i) => i)) {
      const { start, end } = defaultWindow(new Date(2026, month, 15));
      expect(end >= start).toBe(true);
    }
  });
});
