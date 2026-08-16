import * as React from "react";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronsUpDown, ChevronLeft, ChevronRight } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { useIsDesktop } from "@/lib/hooks/useIsDesktop";
import { cn } from "@/lib/utils";

export interface ServerPagination {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}

interface DataTableProps<TData> {
  columns: ColumnDef<TData, unknown>[];
  data: TData[];
  /** When provided, renders server-side page controls in a footer. */
  pagination?: ServerPagination;
  onRowClick?: (row: TData) => void;
  /** Stable row id for keys + click targets. */
  getRowId?: (row: TData) => string;
  className?: string;
  /** Disable client-side sorting (e.g. for already-server-sorted data). */
  enableSorting?: boolean;
  /**
   * Column ids to show on the FACE of each card below `md`. The rest fold into a
   * "Details" disclosure. Defaults to the first three columns, which is a decent
   * guess but rarely the best one — pass the fields a person actually scans for.
   */
  mobilePrimary?: string[];
  /** Singular noun for the card list's accessible label, e.g. "user". */
  mobileItemLabel?: string;
}

/** A column header is usually a plain string; anything else (a sort control, an
 *  icon) has no sensible text form, so the card falls back to the column id
 *  humanised. Cards need a LABEL per value — without one a phone shows a column
 *  of context-free values. */
function headerLabel(columnDef: { header?: unknown; id?: string }, id: string): string {
  const h = columnDef.header;
  if (typeof h === "string") return h;
  return (id || "").replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Shared table. Client-sorts the current page; server pagination is driven by
 * the optional `pagination` prop. Pair with the contract's `{count, results}`
 * envelope (pass `results` as data + `count` as total) or a plain array.
 */
export function DataTable<TData>({
  columns,
  data,
  pagination,
  onRowClick,
  getRowId,
  className,
  enableSorting = true,
  mobilePrimary,
  mobileItemLabel = "row",
}: DataTableProps<TData>) {
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const isDesktop = useIsDesktop();

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: enableSorting ? getSortedRowModel() : undefined,
    enableSorting,
    getRowId: getRowId ? (row) => getRowId(row as TData) : undefined,
    manualPagination: true,
  });

  const totalPages = pagination
    ? Math.max(1, Math.ceil(pagination.total / pagination.pageSize))
    : 1;
  const from = pagination
    ? (pagination.page - 1) * pagination.pageSize + 1
    : 0;
  const to = pagination
    ? Math.min(pagination.page * pagination.pageSize, pagination.total)
    : 0;

  const pager = pagination && pagination.total > pagination.pageSize && (
    <div className="flex items-center justify-between text-xs text-muted-foreground">
      <span className="tabular-nums">
        {from}–{to} of {pagination.total}
      </span>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="icon-sm"
          className="h-11 w-11 md:h-8 md:w-8"
          disabled={pagination.page <= 1}
          onClick={() => pagination.onPageChange(pagination.page - 1)}
          aria-label="Previous page"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="tabular-nums">
          Page {pagination.page} / {totalPages}
        </span>
        <Button
          variant="outline"
          size="icon-sm"
          className="h-11 w-11 md:h-8 md:w-8"
          disabled={pagination.page >= totalPages}
          onClick={() => pagination.onPageChange(pagination.page + 1)}
          aria-label="Next page"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );

  // ── Below md: stacked cards ────────────────────────────────────────────────
  // A 585px table inside a 356px column scrolls sideways inside its own box. It
  // does not break the page, but it does mean a phone user reads a performance
  // review one horizontal swipe at a time. Each row becomes a card carrying the
  // fields worth scanning, with the remainder behind a disclosure.
  if (!isDesktop) {
    const rows = table.getRowModel().rows;
    const allIds = table.getAllLeafColumns().map((c) => c.id);
    const primaryIds = mobilePrimary?.length ? mobilePrimary : allIds.slice(0, 3);

    return (
      <div className={cn("space-y-3", className)}>
        <ul className="space-y-2" aria-label={`${mobileItemLabel} list`}>
          {rows.map((row) => {
            const cells = row.getVisibleCells();
            const primary = cells.filter((c) => primaryIds.includes(c.column.id));
            const rest = cells.filter((c) => !primaryIds.includes(c.column.id));
            const [lead, ...restPrimary] = primary;
            return (
              <li key={row.id}>
                <div
                  className={cn(
                    "rounded-lg border border-border bg-card p-3",
                    onRowClick && "cursor-pointer active:bg-secondary",
                  )}
                  // The whole card stays tappable for pointer/touch convenience,
                  // but it is NOT given role="button". It contains a <details>
                  // disclosure, and a button wrapping another interactive control
                  // is a WCAG "nested-interactive" failure — a screen reader
                  // cannot address the inner control. The accessible, keyboard-
                  // operable action is the lead-field button below; this handler
                  // is the convenience layer on top of it.
                  onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                >
                  {lead &&
                    (onRowClick ? (
                      <button
                        type="button"
                        // The real row action: focusable, announced, and
                        // Enter/Space activated natively.
                        // tap-target: the button is full-width but only ~24px
                        // tall, so it needs the 44px hit area like every other
                        // small control (A9).
                        className="tap-target block w-full text-left text-sm font-semibold text-foreground"
                        onClick={(e) => {
                          e.stopPropagation();
                          onRowClick(row.original);
                        }}
                      >
                        {flexRender(lead.column.columnDef.cell, lead.getContext())}
                      </button>
                    ) : (
                      <div className="text-sm font-semibold text-foreground">
                        {flexRender(lead.column.columnDef.cell, lead.getContext())}
                      </div>
                    ))}
                  {restPrimary.length > 0 && (
                    <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5">
                      {restPrimary.map((cell) => (
                        <div key={cell.id} className="min-w-0">
                          <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                            {headerLabel(cell.column.columnDef, cell.column.id)}
                          </dt>
                          <dd className="truncate text-sm text-foreground">
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  )}
                  {rest.length > 0 && (
                    <details
                      className="mt-2 border-t border-border pt-2"
                      // Stop the disclosure toggle from also firing the card's
                      // row-click and navigating away from what you just opened.
                      onClick={(e) => e.stopPropagation()}
                    >
                      <summary className="cursor-pointer list-none text-xs font-medium text-primary">
                        Details
                      </summary>
                      <dl className="mt-2 space-y-1.5">
                        {rest.map((cell) => (
                          <div key={cell.id} className="flex gap-2">
                            <dt className="w-28 shrink-0 text-xs uppercase tracking-wide text-muted-foreground">
                              {headerLabel(cell.column.columnDef, cell.column.id)}
                            </dt>
                            <dd className="min-w-0 flex-1 text-sm text-foreground">
                              {flexRender(cell.column.columnDef.cell, cell.getContext())}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    </details>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
        {pager}
      </div>
    );
  }

  // ── md and up: the table, unchanged ────────────────────────────────────────
  return (
    <div className={cn("space-y-3", className)}>
      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id} className="hover:bg-transparent">
                {hg.headers.map((header) => {
                  const canSort =
                    enableSorting && header.column.getCanSort();
                  const sorted = header.column.getIsSorted();
                  return (
                    <TableHead key={header.id}>
                      {header.isPlaceholder ? null : canSort ? (
                        <button
                          type="button"
                          className="inline-flex items-center gap-1 hover:text-foreground"
                          onClick={header.column.getToggleSortingHandler()}
                        >
                          {flexRender(
                            header.column.columnDef.header,
                            header.getContext(),
                          )}
                          {sorted === "asc" ? (
                            <ArrowUp className="h-3 w-3" />
                          ) : sorted === "desc" ? (
                            <ArrowDown className="h-3 w-3" />
                          ) : (
                            <ChevronsUpDown className="h-3 w-3 opacity-40" />
                          )}
                        </button>
                      ) : (
                        flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )
                      )}
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.map((row) => (
              <TableRow
                key={row.id}
                onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                className={cn(onRowClick && "cursor-pointer")}
              >
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {pager}
    </div>
  );
}
