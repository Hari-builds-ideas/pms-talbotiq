import { PersonName } from "@/components/PersonName";
import { cn } from "@/lib/utils";

interface Placement {
  employee: string;
  box: number;
}

/** box → talent tone (top-right strong, bottom-left at-risk). */
const BOX_TONE: Record<number, string> = {
  9: "bg-success-subtle/70 border-success/30",
  8: "bg-success-subtle/60 border-success/30",
  6: "bg-success-subtle/50 border-success/20",
  7: "bg-warning-subtle/50 border-warning/20",
  5: "bg-warning-subtle/40 border-warning/20",
  3: "bg-warning-subtle/40 border-warning/20",
  4: "bg-danger-subtle/40 border-danger/20",
  2: "bg-danger-subtle/50 border-danger/20",
  1: "bg-danger-subtle/60 border-danger/30",
};

const BOX_LABEL: Record<number, string> = {
  9: "Star",
  8: "High potential",
  7: "Potential gem",
  6: "High performer",
  5: "Core player",
  4: "Inconsistent",
  3: "Trusted pro",
  2: "Up or out",
  1: "At risk",
};

// Rows top→bottom = potential HIGH→LOW; cols left→right = performance LOW→HIGH.
const ROWS = [
  [7, 8, 9],
  [4, 5, 6],
  [1, 2, 3],
];

export function NineBoxGrid({ placements }: { placements: Placement[] }) {
  const byBox = new Map<number, string[]>();
  for (const p of placements) {
    const list = byBox.get(p.box) ?? [];
    list.push(p.employee);
    byBox.set(p.box, list);
  }

  return (
    <div className="flex gap-3">
      {/* Potential axis label */}
      <div className="flex flex-col items-center justify-center">
        <span className="rotate-180 text-2xs font-semibold uppercase tracking-wide text-muted-foreground [writing-mode:vertical-rl]">
          Potential →
        </span>
      </div>

      <div className="flex-1 space-y-3">
        <div className="grid grid-cols-3 gap-2">
          {ROWS.flat().map((box) => {
            const people = byBox.get(box) ?? [];
            return (
              <div
                key={box}
                className={cn(
                  "flex min-h-28 flex-col rounded-lg border p-2.5",
                  BOX_TONE[box],
                )}
              >
                <div className="mb-1.5 flex items-center justify-between">
                  <span className="text-2xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {BOX_LABEL[box]}
                  </span>
                  <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-card px-1.5 text-2xs font-semibold tabular-nums">
                    {people.length}
                  </span>
                </div>
                <ul className="space-y-1">
                  {people.slice(0, 5).map((id, i) => (
                    <li key={`${id}-${i}`} className="truncate text-xs">
                      <PersonName id={id} />
                    </li>
                  ))}
                  {people.length > 5 && (
                    <li className="text-2xs text-muted-foreground">+{people.length - 5} more</li>
                  )}
                </ul>
              </div>
            );
          })}
        </div>
        <div className="text-center text-2xs font-semibold uppercase tracking-wide text-muted-foreground">
          Performance →
        </div>
      </div>
    </div>
  );
}
