import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { useDirectory } from "@/lib/hooks/useDirectory";
import { initials, looksLikeUuid } from "@/lib/format";
import { cn } from "@/lib/utils";

interface PersonNameProps {
  id?: string | null;
  /** A server-resolved label (e.g. `reviewer_name`). Preferred over the
   * client directory — it's correct even for a user outside the caller's
   * org-tree scope. */
  name?: string | null;
  /** Show a small avatar alongside the name. */
  withAvatar?: boolean;
  className?: string;
}

/**
 * Renders a person's display name. Prefers the server-resolved `name`, falls
 * back to the (scope-limited) directory, and NEVER renders a raw UUID — an
 * unresolvable id shows "Unknown" rather than leaking an identifier.
 */
export function PersonName({ id, name, withAvatar, className }: PersonNameProps) {
  const { nameOf } = useDirectory();
  const candidate = name?.trim() || nameOf(id);
  const display = !candidate || looksLikeUuid(candidate) ? "Unknown" : candidate;
  if (!withAvatar) return <span className={className}>{display}</span>;
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <Avatar className="h-6 w-6">
        <AvatarFallback className="text-[10px]">{initials(display)}</AvatarFallback>
      </Avatar>
      <span className="truncate">{display}</span>
    </span>
  );
}
