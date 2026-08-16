/**
 * DataTable's responsive split.
 *
 * Below md every table screen renders stacked cards instead of a table: a 585px
 * table inside a 356px column scrolls sideways in its own box, so a phone user
 * read a record one horizontal swipe at a time. These lock the behaviour in,
 * including the bits that are easy to regress — the labels, the disclosure, and
 * keyboard activation of a card.
 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "./DataTable";

interface Row {
  id: string;
  name: string;
  role: string;
  status: string;
  note: string;
}

const ROWS: Row[] = [
  { id: "1", name: "Ada Lovelace", role: "MANAGER", status: "Active", note: "first" },
  { id: "2", name: "Reza Khan", role: "EMPLOYEE", status: "Inactive", note: "second" },
];

const COLUMNS: ColumnDef<Row, unknown>[] = [
  { accessorKey: "name", header: "Name" },
  { accessorKey: "role", header: "Role" },
  { accessorKey: "status", header: "Status" },
  { accessorKey: "note", header: "Note" },
];

/** jsdom implements no matchMedia; install the one each test needs. */
function setViewport(isDesktop: boolean) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: isDesktop,
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

describe("DataTable — desktop", () => {
  it("renders a real table at md and up", () => {
    setViewport(true);
    render(<DataTable columns={COLUMNS} data={ROWS} getRowId={(r) => r.id} />);
    expect(document.querySelector("table")).not.toBeNull();
    expect(document.querySelectorAll("tbody tr")).toHaveLength(2);
  });
});

describe("DataTable — below md", () => {
  it("renders cards, not a table", () => {
    setViewport(false);
    render(
      <DataTable
        columns={COLUMNS}
        data={ROWS}
        getRowId={(r) => r.id}
        mobileItemLabel="user"
      />,
    );
    expect(document.querySelector("table")).toBeNull();
    const list = screen.getByRole("list", { name: "user list" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
  });

  it("shows the named primary fields on the card face", () => {
    setViewport(false);
    render(
      <DataTable
        columns={COLUMNS}
        data={ROWS}
        getRowId={(r) => r.id}
        mobilePrimary={["name", "status"]}
      />,
    );
    const first = screen.getAllByRole("listitem")[0];
    // Lead field is the heading; the other primary field is labelled.
    expect(within(first).getByText("Ada Lovelace")).toBeTruthy();
    expect(within(first).getByText("Status")).toBeTruthy();
    expect(within(first).getByText("Active")).toBeTruthy();
  });

  it("folds the non-primary fields behind a Details disclosure", () => {
    setViewport(false);
    render(
      <DataTable
        columns={COLUMNS}
        data={ROWS}
        getRowId={(r) => r.id}
        mobilePrimary={["name", "status"]}
      />,
    );
    const first = screen.getAllByRole("listitem")[0];
    expect(within(first).getByText("Details")).toBeTruthy();
    // Role and Note are not primary, so they live inside the disclosure.
    const details = first.querySelector("details")!;
    expect(within(details as HTMLElement).getByText("MANAGER")).toBeTruthy();
    expect(within(details as HTMLElement).getByText("first")).toBeTruthy();
  });

  it("labels every value — a column of bare values is unreadable on a phone", () => {
    setViewport(false);
    render(
      <DataTable columns={COLUMNS} data={ROWS} getRowId={(r) => r.id} mobilePrimary={["name", "role"]} />,
    );
    const first = screen.getAllByRole("listitem")[0];
    // The header text becomes the value's label.
    expect(within(first).getByText("Role")).toBeTruthy();
    expect(within(first).getByText("Status")).toBeTruthy();
    expect(within(first).getByText("Note")).toBeTruthy();
  });

  it("exposes the row action as a real focusable button", () => {
    setViewport(false);
    const onRowClick = vi.fn();
    render(
      <DataTable columns={COLUMNS} data={ROWS} getRowId={(r) => r.id} onRowClick={onRowClick} />,
    );
    // The lead field is a <button>, so it is reachable by keyboard and activated
    // by Enter/Space natively. The card itself must NOT be role=button: it
    // contains a <details> disclosure, and nesting interactive controls is a
    // WCAG failure a screen reader cannot work around.
    const action = screen.getByRole("button", { name: "Ada Lovelace" });
    expect(action.tagName).toBe("BUTTON");
    fireEvent.click(action);
    expect(onRowClick).toHaveBeenCalledWith(ROWS[0]);

    const card = action.closest("li")!.firstElementChild!;
    expect(card.getAttribute("role")).toBeNull();
  });

  it("does not navigate when the Details disclosure is opened", () => {
    setViewport(false);
    const onRowClick = vi.fn();
    render(
      <DataTable
        columns={COLUMNS}
        data={ROWS}
        getRowId={(r) => r.id}
        onRowClick={onRowClick}
        mobilePrimary={["name"]}
      />,
    );
    // Opening the disclosure must not also fire the card's row-click and take
    // the user away from what they just expanded.
    fireEvent.click(screen.getAllByText("Details")[0]);
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it("keeps the pager in the card layout", () => {
    setViewport(false);
    render(
      <DataTable
        columns={COLUMNS}
        data={ROWS}
        getRowId={(r) => r.id}
        pagination={{ page: 1, pageSize: 2, total: 10, onPageChange: vi.fn() }}
      />,
    );
    expect(screen.getByLabelText("Next page")).toBeTruthy();
    expect(screen.getByLabelText("Previous page")).toBeTruthy();
  });
});
