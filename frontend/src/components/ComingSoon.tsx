import { Hammer } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState } from "@/components/EmptyState";

/** Placeholder for screens scheduled in a later build phase. */
export function ComingSoon({
  title,
  description,
  phase,
}: {
  title: string;
  description?: string;
  phase?: string;
}) {
  return (
    <div>
      <PageHeader title={title} description={description} />
      <EmptyState
        icon={Hammer}
        title="Arriving in a later build phase"
        description={
          phase
            ? `This area is part of ${phase}. The foundation, design system and data layer it builds on are already in place.`
            : "This area is being built. The foundation it relies on is already in place."
        }
      />
    </div>
  );
}
