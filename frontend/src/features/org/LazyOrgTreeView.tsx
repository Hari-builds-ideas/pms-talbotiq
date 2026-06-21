import * as React from "react";
import { ChevronDown, ChevronRight, Loader2, Users } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { ErrorState } from "@/components/ErrorState";
import { LinesSkeleton } from "@/components/Skeletons";
import { ROLE_LABEL, type Role } from "@/lib/enums";
import { initials } from "@/lib/format";
import { cn } from "@/lib/utils";
import { orgApi } from "@/lib/api/endpoints";
import { allChildrenLoaded, childrenOf, normalizeOrgTree } from "@/lib/org";
import type { OrgNode } from "@/lib/types";

interface Props {
  selectedId?: string | null;
  onSelect: (id: string) => void;
}

/**
 * Expand-on-demand org tree for broad-scope roles (HRBP/Admin), whose tenant tree
 * can be large. The initial fetch pulls only the top two levels (`?depth=1`);
 * expanding a node fetches that node's children (`?root=<id>&depth=1`) and merges
 * them in. A node shows an expand affordance whenever its `direct_report_ids` is
 * non-empty — even before its children are fetched. Narrow scopes keep the
 * whole-tree `OrgTreeView` (their line is small).
 */
export function LazyOrgTreeView({ selectedId, onSelect }: Props) {
  const [nodes, setNodes] = React.useState<Record<string, OrgNode>>({});
  const [roots, setRoots] = React.useState<string[]>([]);
  const [status, setStatus] = React.useState<"loading" | "error" | "ready">("loading");
  const [error, setError] = React.useState<unknown>(null);
  const [loading, setLoading] = React.useState<Set<string>>(new Set());

  const init = React.useCallback(() => {
    setStatus("loading");
    orgApi
      .tree({ depth: 1 })
      .then(normalizeOrgTree)
      .then((t) => {
        setNodes(t.nodes);
        setRoots(t.roots);
        setStatus("ready");
      })
      .catch((e) => {
        setError(e);
        setStatus("error");
      });
  }, []);

  React.useEffect(() => init(), [init]);

  const expand = React.useCallback(async (id: string) => {
    setLoading((s) => new Set(s).add(id));
    try {
      const t = normalizeOrgTree(await orgApi.tree({ root: id, depth: 1 }));
      setNodes((prev) => ({ ...prev, ...t.nodes }));
    } finally {
      setLoading((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  }, []);

  if (status === "loading") return <LinesSkeleton lines={8} />;
  if (status === "error") return <ErrorState error={error} onRetry={init} compact />;

  return (
    <div className="space-y-0.5">
      {roots.map((id) => (
        <LazyNode
          key={id}
          id={id}
          depth={0}
          nodes={nodes}
          loading={loading}
          onExpand={expand}
          selectedId={selectedId}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}

function LazyNode({
  id,
  depth,
  nodes,
  loading,
  onExpand,
  selectedId,
  onSelect,
}: {
  id: string;
  depth: number;
  nodes: Record<string, OrgNode>;
  loading: Set<string>;
  onExpand: (id: string) => void;
  selectedId?: string | null;
  onSelect: (id: string) => void;
}) {
  // Roots render open (their children came with the initial depth=1 fetch);
  // deeper nodes start collapsed and fetch their children on first expand.
  const [open, setOpen] = React.useState(depth < 1);
  const node = nodes[id];
  if (!node) return null;
  const hasKids = node.direct_report_ids.length > 0;
  const kids = childrenOf(id, nodes);
  const isLoading = loading.has(id);

  function toggle() {
    if (!hasKids) return;
    const next = !open;
    setOpen(next);
    if (next && !allChildrenLoaded(id, nodes) && !isLoading) onExpand(id);
  }

  return (
    <div>
      <div
        className={cn(
          "group flex items-center gap-2 rounded-md py-1.5 pr-2 transition-colors hover:bg-secondary/60",
          selectedId === id && "bg-accent",
        )}
        style={{ paddingLeft: depth * 20 + 4 }}
      >
        <button
          type="button"
          onClick={toggle}
          className={cn(
            "flex h-5 w-5 shrink-0 items-center justify-center rounded text-muted-foreground",
            hasKids ? "hover:bg-secondary" : "invisible",
          )}
          aria-label={open ? "Collapse" : "Expand"}
        >
          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : open ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
        </button>
        <button
          type="button"
          onClick={() => onSelect(id)}
          className="flex min-w-0 flex-1 items-center gap-2.5 text-left"
        >
          <Avatar className="h-7 w-7">
            <AvatarFallback className="text-[10px]">{initials(node.display || node.email)}</AvatarFallback>
          </Avatar>
          <span className="min-w-0">
            <span className="block truncate text-sm font-medium">{node.display || node.email}</span>
            <span className="block truncate text-2xs text-muted-foreground">{node.email}</span>
          </span>
          <Badge variant="secondary" className="ml-1 shrink-0">{ROLE_LABEL[node.role as Role]}</Badge>
          <span className="ml-auto flex shrink-0 items-center gap-1.5 text-2xs text-muted-foreground">
            <Users className="h-3 w-3" />
            {node.headcount}
            {node.vacancies > 0 && (
              <Badge variant="warning" className="ml-1">{node.vacancies} open</Badge>
            )}
          </span>
        </button>
      </div>
      {open && hasKids && (
        <div>
          {kids.map((kid) => (
            <LazyNode
              key={kid.id}
              id={kid.id}
              depth={depth + 1}
              nodes={nodes}
              loading={loading}
              onExpand={onExpand}
              selectedId={selectedId}
              onSelect={onSelect}
            />
          ))}
          {isLoading && kids.length === 0 && (
            <div
              className="flex items-center gap-1.5 py-1.5 text-2xs text-muted-foreground"
              style={{ paddingLeft: (depth + 1) * 20 + 4 }}
            >
              <Loader2 className="h-3 w-3 animate-spin" /> Loading…
            </div>
          )}
        </div>
      )}
    </div>
  );
}
