import * as React from "react";
import { GripVertical, RotateCcw } from "lucide-react";
import { PersonName } from "@/components/PersonName";
import { bucketByEffectiveBox } from "@/lib/nineBox";
import { cn } from "@/lib/utils";

/** The minimal cell contract the grid renders. The succession 9-box passes full
 *  placements (with id + override fields → interactive); the analytics calibration
 *  grid passes just employee + box (read-only). */
export interface NineBoxCell {
  id?: string;
  employee: string;
  employee_name?: string | null;
  box: number;
  effective_box?: number;
  is_overridden?: boolean;
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

interface NineBoxGridProps {
  placements: NineBoxCell[];
  /** When true (HRBP/Admin), chips can be dragged between cells to set a human
   *  override, and overridden chips can be reset. Otherwise the grid is read-only. */
  canOverride?: boolean;
  onReposition?: (placementId: string, box: number) => void;
  onClearOverride?: (placementId: string) => void;
  /** A placement id currently saving — its chip shows a pending state. */
  pendingId?: string | null;
}

export function NineBoxGrid({
  placements,
  canOverride = false,
  onReposition,
  onClearOverride,
  pendingId,
}: NineBoxGridProps) {
  const byBox = bucketByEffectiveBox(placements);
  const [dragOver, setDragOver] = React.useState<number | null>(null);

  function handleDrop(e: React.DragEvent, box: number) {
    e.preventDefault();
    setDragOver(null);
    const id = e.dataTransfer.getData("text/plain");
    const p = placements.find((x) => x.id === id);
    if (p?.id && (p.effective_box ?? p.box) !== box) onReposition?.(p.id, box);
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
                onDragOver={canOverride ? (e) => { e.preventDefault(); setDragOver(box); } : undefined}
                onDragLeave={canOverride ? () => setDragOver((b) => (b === box ? null : b)) : undefined}
                onDrop={canOverride ? (e) => handleDrop(e, box) : undefined}
                className={cn(
                  "flex min-h-28 flex-col rounded-lg border p-2.5 transition-colors",
                  BOX_TONE[box],
                  canOverride && dragOver === box && "ring-2 ring-primary ring-offset-1",
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
                  {people.map((p) => (
                    <li
                      key={p.id ?? p.employee}
                      draggable={canOverride}
                      onDragStart={
                        canOverride ? (e) => e.dataTransfer.setData("text/plain", p.id ?? "") : undefined
                      }
                      className={cn(
                        "group flex items-center gap-1 truncate rounded px-1 py-0.5 text-xs",
                        canOverride && "cursor-grab hover:bg-card/60 active:cursor-grabbing",
                        pendingId && pendingId === p.id && "opacity-50",
                      )}
                      title={p.is_overridden ? "Human override — drag to move, or reset to computed" : undefined}
                    >
                      {canOverride && (
                        <GripVertical className="h-3 w-3 shrink-0 text-muted-foreground opacity-0 group-hover:opacity-100" />
                      )}
                      <span className="truncate">
                        <PersonName id={p.employee} name={p.employee_name} />
                      </span>
                      {p.is_overridden && (
                        <span
                          className="ml-auto flex shrink-0 items-center gap-0.5 text-2xs text-primary"
                          title={`Computed box ${p.box}, moved to ${p.effective_box}`}
                        >
                          ●
                          {canOverride && onClearOverride && p.id && (
                            <button
                              type="button"
                              onClick={() => onClearOverride(p.id as string)}
                              aria-label="Reset to computed placement"
                              className="rounded p-0.5 hover:text-foreground"
                            >
                              <RotateCcw className="h-3 w-3" />
                            </button>
                          )}
                        </span>
                      )}
                    </li>
                  ))}
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
