import * as React from "react";
import { Check, X } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { LinesSkeleton } from "@/components/Skeletons";
import { ErrorState } from "@/components/ErrorState";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { RouteTracker } from "./RouteTracker";
import { useRoute, useStepMutations } from "./useApprovals";
import { notifyError, notifySuccess } from "@/lib/toast";

interface RouteSheetProps {
  routeId: string | null;
  /** The step the current user may act on (from the inbox), if any. */
  actionStepId?: string | null;
  onOpenChange: (open: boolean) => void;
}

export function RouteSheet({ routeId, actionStepId, onOpenChange }: RouteSheetProps) {
  const route = useRoute(routeId);
  const { approve, reject } = useStepMutations(routeId);
  const [rejectOpen, setRejectOpen] = React.useState(false);

  // The actionable step must still be pending after a refetch.
  const step = route.data?.step_instances.find((s) => s.id === actionStepId);
  const canAct = step?.status === "PENDING";

  async function doApprove() {
    if (!step?.id) return;
    try {
      const updated = await approve.mutateAsync({ id: step.id });
      notifySuccess(
        updated.status === "APPROVED" ? "Route approved" : "Step approved",
        updated.status === "APPROVED" ? "All required steps are complete." : "The route advanced to the next step.",
      );
    } catch (err) {
      notifyError(err);
      void route.refetch();
    }
  }

  return (
    <>
      <Sheet open={Boolean(routeId)} onOpenChange={onOpenChange}>
        <SheetContent side="right" className="w-full sm:max-w-lg">
          <SheetHeader>
            <SheetTitle>Approval route</SheetTitle>
            <SheetDescription>
              Track each step and act on the one assigned to you.
            </SheetDescription>
          </SheetHeader>

          <div className="flex-1 overflow-y-auto scrollbar-thin p-5">
            {route.isLoading ? (
              <LinesSkeleton lines={6} />
            ) : route.isError ? (
              <ErrorState error={route.error} onRetry={() => route.refetch()} compact />
            ) : route.data ? (
              <RouteTracker route={route.data} />
            ) : null}
          </div>

          {canAct && (
            <SheetFooter>
              <Button
                variant="outline"
                className="text-danger"
                onClick={() => setRejectOpen(true)}
                disabled={approve.isPending}
              >
                <X className="h-4 w-4" />
                Reject
              </Button>
              <Button onClick={doApprove} loading={approve.isPending}>
                <Check className="h-4 w-4" />
                Approve step
              </Button>
            </SheetFooter>
          )}
        </SheetContent>
      </Sheet>

      <ConfirmDialog
        open={rejectOpen}
        onOpenChange={setRejectOpen}
        title="Reject this step?"
        description="Rejecting ends the route and returns the artifact to its author."
        confirmLabel="Reject step"
        destructive
        reason={{ label: "Reason", placeholder: "Explain why you're rejecting…", required: true }}
        onConfirm={async (reason) => {
          if (!step?.id) return;
          await reject.mutateAsync({ id: step.id, comment: reason ?? "" });
          notifySuccess("Step rejected", "The route has ended.");
        }}
      />
    </>
  );
}
