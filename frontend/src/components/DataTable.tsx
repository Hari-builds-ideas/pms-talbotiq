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
}: DataTableProps<TData>) {
  const [sorting, setSorting] = React.useState<SortingState>([]);

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

      {pagination && pagination.total > pagination.pageSize && (
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span className="tabular-nums">
            {from}–{to} of {pagination.total}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon-sm"
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
              disabled={pagination.page >= totalPages}
              onClick={() => pagination.onPageChange(pagination.page + 1)}
              aria-label="Next page"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
