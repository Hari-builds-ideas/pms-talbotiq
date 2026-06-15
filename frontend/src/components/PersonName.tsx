import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { useDirectory } from "@/lib/hooks/useDirectory";
import { initials } from "@/lib/format";
import { cn } from "@/lib/utils";

interface PersonNameProps {
  id?: string | null;
  /** Show a small avatar alongside the name. */
  withAvatar?: boolean;
  className?: string;
}

/** Resolves a user UUID to its display name (+ optional avatar). */
export function PersonName({ id, withAvatar, className }: PersonNameProps) {
  const { nameOf } = useDirectory();
  const name = nameOf(id);
  if (!withAvatar) return <span className={className}>{name}</span>;
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <Avatar className="h-6 w-6">
        <AvatarFallback className="text-[10px]">{initials(name)}</AvatarFallback>
      </Avatar>
      <span className="truncate">{name}</span>
    </span>
  );
}
