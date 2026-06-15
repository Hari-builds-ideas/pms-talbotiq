import { cn } from "@/lib/utils";

/** A shimmering placeholder block — used instead of spinners for loading. */
function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("skeleton-shimmer rounded-md", className)}
      aria-hidden
      {...props}
    />
  );
}

export { Skeleton };
