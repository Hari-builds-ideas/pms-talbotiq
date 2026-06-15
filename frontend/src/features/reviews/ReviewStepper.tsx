import { Stepper, type StepItem } from "@/components/Stepper";
import type { ReviewState } from "@/lib/enums";

/**
 * Renders the review lifecycle as a horizontal stepper.
 * Happy path: Draft → Pending review → Approved → Finalized.
 * REJECTED is shown as a failed "Pending review" stage; AI_DRAFTING / EDITING
 * annotate the Draft stage as in-progress.
 */
const STAGES = ["Draft", "Pending review", "Approved", "Finalized"] as const;

function stageIndex(state: ReviewState): number {
  switch (state) {
    case "DRAFT":
    case "EDITING":
    case "AI_DRAFTING":
      return 0;
    case "PENDING_HUMAN_REVIEW":
    case "REJECTED":
      return 1;
    case "APPROVED":
      return 2;
    case "FINALIZED":
      return 3;
    default:
      return 0;
  }
}

export function ReviewStepper({ state }: { state: ReviewState }) {
  const current = stageIndex(state);
  const rejected = state === "REJECTED";
  const finalized = state === "FINALIZED";

  const caption: Record<number, string | undefined> = {
    0: state === "AI_DRAFTING" ? "AI drafting…" : state === "EDITING" ? "Editing" : undefined,
    1: rejected ? "Rejected" : undefined,
  };

  const steps: StepItem[] = STAGES.map((label, i) => {
    let stepState: StepItem["state"];
    if (rejected && i === 1) stepState = "rejected";
    else if (finalized) stepState = "done";
    else if (i < current) stepState = "done";
    else if (i === current) stepState = "current";
    else stepState = "upcoming";
    return { key: label, label, state: stepState, caption: caption[i] };
  });

  return <Stepper steps={steps} />;
}
