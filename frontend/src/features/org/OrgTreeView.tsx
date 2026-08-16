import * as React from "react";
import { ChevronDown, ChevronRight, Users } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { ROLE_LABEL, type Role } from "@/lib/enums";
import { initials } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { OrgTree } from "@/lib/types";

interface OrgTreeViewProps {
  tree: OrgTree;
  selectedId?: string | null;
  onSelect: (id: string) => void;
}

export function OrgTreeView({ tree, selectedId, onSelect }: OrgTreeViewProps) {
  const childrenMap = React.useMemo(() => {
    const map: Record<string, string[]> = {};
    for (const [parent, child] of tree.edges) {
      (map[parent] ??= []).push(child);
    }
    return map;
  }, [tree.edges]);

  return (
    <div className="space-y-0.5">
      {tree.roots.map((rootId) => (
        <TreeNode
          key={rootId}
          id={rootId}
          depth={0}
          tree={tree}
          childrenMap={childrenMap}
          selectedId={selectedId}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}

function TreeNode({
  id,
  depth,
  tree,
  childrenMap,
  selectedId,
  onSelect,
}: {
  id: string;
  depth: number;
  tree: OrgTree;
  childrenMap: Record<string, string[]>;
  selectedId?: string | null;
  onSelect: (id: string) => void;
}) {
  const [open, setOpen] = React.useState(depth < 2);
  const node = tree.nodes[id];
  if (!node) return null;
  const kids = childrenMap[id] ?? [];
  const hasKids = kids.length > 0;

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
          onClick={() => hasKids && setOpen((o) => !o)}
          className={cn(
            "tap-target flex h-5 w-5 shrink-0 items-center justify-center rounded text-muted-foreground",
            hasKids ? "hover:bg-secondary" : "invisible",
          )}
          aria-label={open ? "Collapse" : "Expand"}
        >
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </button>
        <button
          type="button"
          onClick={() => onSelect(id)}
          className="tap-target flex min-w-0 flex-1 items-center gap-2.5 text-left"
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
            <TreeNode
              key={kid}
              id={kid}
              depth={depth + 1}
              tree={tree}
              childrenMap={childrenMap}
              selectedId={selectedId}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}
