import * as React from "react";
import { Check, Circle, Dot, X } from "lucide-react";
import { cn } from "@/lib/utils";

export type StepState = "done" | "current" | "upcoming" | "rejected";

export interface StepItem {
  key: string;
  label: string;
  caption?: string;
  state: StepState;
}

/** Horizontal stepper for a linear lifecycle (e.g. the review state machine). */
export function Stepper({
  steps,
  className,
}: {
  steps: StepItem[];
  className?: string;
}) {
  return (
    <ol className={cn("flex w-full items-start", className)}>
      {steps.map((step, i) => {
        const isLast = i === steps.length - 1;
        return (
          <li key={step.key} className="flex flex-1 flex-col items-center">
            <div className="flex w-full items-center">
              <div
                className={cn(
                  "h-px flex-1",
                  i === 0 ? "opacity-0" : "",
                  step.state === "done" || step.state === "current"
                    ? "bg-primary"
                    : "bg-border",
                )}
              />
              <span
                className={cn(
                  "flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-xs font-semibold transition-colors",
                  step.state === "done" &&
                    "border-primary bg-primary text-primary-foreground",
                  step.state === "current" &&
                    "border-primary bg-primary/10 text-primary",
                  step.state === "upcoming" &&
                    "border-border bg-card text-muted-foreground",
                  step.state === "rejected" &&
                    "border-danger bg-danger text-danger-foreground",
                )}
              >
                {step.state === "done" ? (
                  <Check className="h-4 w-4" />
                ) : step.state === "rejected" ? (
                  <X className="h-4 w-4" />
                ) : step.state === "current" ? (
                  <Dot className="h-6 w-6" />
                ) : (
                  i + 1
                )}
              </span>
              <div
                className={cn(
                  "h-px flex-1",
                  isLast ? "opacity-0" : "",
                  step.state === "done" ? "bg-primary" : "bg-border",
                )}
              />
            </div>
            <div className="mt-2 px-1 text-center">
              <p
                className={cn(
                  "text-xs font-medium",
                  step.state === "upcoming"
                    ? "text-muted-foreground"
                    : "text-foreground",
                )}
              >
                {step.label}
              </p>
              {step.caption && (
                <p className="mt-0.5 text-2xs text-muted-foreground">
                  {step.caption}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export interface TimelineItem {
  key: string;
  icon?: React.ReactNode;
  title: React.ReactNode;
  meta?: React.ReactNode;
  body?: React.ReactNode;
  /** Tone for the node dot. */
  tone?: "default" | "success" | "danger" | "warning" | "info" | "muted";
}

const TONE_DOT: Record<NonNullable<TimelineItem["tone"]>, string> = {
  default: "bg-primary text-primary-foreground",
  success: "bg-success text-success-foreground",
  danger: "bg-danger text-danger-foreground",
  warning: "bg-warning text-warning-foreground",
  info: "bg-info text-info-foreground",
  muted: "bg-muted text-muted-foreground",
};

/** Vertical timeline for transition history / approval-route steps. */
export function Timeline({
  items,
  className,
}: {
  items: TimelineItem[];
  className?: string;
}) {
  return (
    <ol className={cn("relative space-y-0", className)}>
      {items.map((item, i) => {
        const isLast = i === items.length - 1;
        return (
          <li key={item.key} className="relative flex gap-3 pb-5 last:pb-0">
            {!isLast && (
              <span
                className="absolute left-[13px] top-7 h-[calc(100%-1rem)] w-px bg-border"
                aria-hidden
              />
            )}
            <span
              className={cn(
                "z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs [&_svg]:h-3.5 [&_svg]:w-3.5",
                TONE_DOT[item.tone ?? "default"],
              )}
            >
              {item.icon ?? <Circle className="h-2 w-2 fill-current" />}
            </span>
            <div className="min-w-0 flex-1 pt-0.5">
              <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                <div className="text-sm font-medium text-foreground">
                  {item.title}
                </div>
                {item.meta && (
                  <div className="text-xs text-muted-foreground">{item.meta}</div>
                )}
              </div>
              {item.body && (
                <div className="mt-1 text-sm text-muted-foreground">
                  {item.body}
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
