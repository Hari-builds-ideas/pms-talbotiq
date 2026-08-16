/**
 * WCAG 2.1 A/AA guard at a MOBILE viewport.
 *
 * The existing a11y suite renders with jsdom's default (absent) matchMedia, which
 * the shell reads as desktop — so it exercises the table layout and the inline
 * sidebar, and never sees the two structures PHASE A introduced: the modal
 * navigation drawer and the DataTable card list. Those are exactly the shapes
 * where mobile a11y goes wrong (a dialog with no accessible name, a list of cards
 * with no labels, a disclosure inside a clickable card).
 */
import { render } from "@testing-library/react";
import { fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/DataTable";
import { axeViolations, summarize, renderInShell } from "./harness";

vi.mock("@/lib/auth/AuthContext", () => ({
  useAuth: () => ({
    me: {
      id: "u1",
      email: "admin@acme.test",
      display: "Ada Admin",
      display_name: "Ada Admin",
      role: "ADMIN",
      tenant_name: "Acme",
      tenant_slug: "acme",
      mfa_enabled: false,
      manager_id: null,
    },
    status: "authenticated",
    features: {},
    hasFeature: () => true,
    atLeast: () => true,
    can: () => true,
    logout: vi.fn(),
    completeLogin: vi.fn(),
    refreshFeatures: vi.fn(),
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));

/** Force the shell and DataTable onto their below-md branches. */
function setMobileViewport() {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false, // never desktop
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}

afterEach(() => {
  // @ts-expect-error — restore jsdom's real default (absent).
  delete window.matchMedia;
});

interface Row { id: string; name: string; role: string; status: string; note: string }
const ROWS: Row[] = [
  { id: "1", name: "Ada Lovelace", role: "MANAGER", status: "Active", note: "n1" },
  { id: "2", name: "Reza Khan", role: "EMPLOYEE", status: "Inactive", note: "n2" },
];
const COLUMNS: ColumnDef<Row, unknown>[] = [
  { accessorKey: "name", header: "Name" },
  { accessorKey: "role", header: "Role" },
  { accessorKey: "status", header: "Status" },
  { accessorKey: "note", header: "Note" },
];

describe("WCAG 2.1 A/AA — mobile layouts", () => {
  it("has no violations with the shell at a phone width", async () => {
    setMobileViewport();
    const { container } = renderInShell(<div>content</div>, "/");
    const v = await axeViolations(container);
    expect(v, summarize(v)).toHaveLength(0);
  });

  it("has no violations with the navigation drawer OPEN", async () => {
    setMobileViewport();
    const { container } = renderInShell(<div>content</div>, "/");
    fireEvent.click(screen.getByLabelText("Toggle navigation"));
    // The drawer is a modal surface — this is where a missing accessible name or
    // a mis-set aria-modal shows up.
    expect(document.querySelector("aside")?.getAttribute("role")).toBe("dialog");
    const v = await axeViolations(container);
    expect(v, summarize(v)).toHaveLength(0);
  });

  it("has no violations in the DataTable card layout", async () => {
    setMobileViewport();
    const { container } = render(
      <DataTable
        columns={COLUMNS}
        data={ROWS}
        getRowId={(r) => r.id}
        mobilePrimary={["name", "status"]}
        mobileItemLabel="user"
        onRowClick={vi.fn()}
      />,
    );
    const v = await axeViolations(container);
    expect(v, summarize(v)).toHaveLength(0);
  });
});
