import * as React from "react";
import { Plus, Trash2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Field } from "@/components/Field";
import { useWorkflowMutations } from "./useApprovals";
import { useDirectory } from "@/lib/hooks/useDirectory";
import { ROLES, ROLE_LABEL, type Role } from "@/lib/enums";
import { notifySuccess } from "@/lib/toast";
import { mapApiError } from "@/lib/errors";
import type { ApprovalStepTemplate } from "@/lib/types";

const ARTIFACT_TYPES = ["review", "jd"] as const;

interface DraftStep {
  approver_kind: "ROLE" | "NAMED";
  approver_role: Role;
  approver_user: string | null;
  required: boolean;
  timeout_hours: number;
}

const newStep = (): DraftStep => ({
  approver_kind: "ROLE",
  approver_role: "MANAGER",
  approver_user: null,
  required: true,
  timeout_hours: 48,
});

export function WorkflowDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const { create } = useWorkflowMutations();
  const { nodes } = useDirectory();
  const people = Object.values(nodes);

  const [name, setName] = React.useState("");
  const [artifact, setArtifact] = React.useState<string>("review");
  const [mode, setMode] = React.useState<"SEQUENTIAL" | "PARALLEL">("SEQUENTIAL");
  const [steps, setSteps] = React.useState<DraftStep[]>([newStep()]);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (open) {
      setName(""); setArtifact("review"); setMode("SEQUENTIAL");
      setSteps([newStep()]); setError(null);
    }
  }, [open]);

  function patchStep(i: number, patch: Partial<DraftStep>) {
    setSteps((prev) => prev.map((s, idx) => (idx === i ? { ...s, ...patch } : s)));
  }

  async function submit() {
    setError(null);
    if (!name.trim()) {
      setError("Give the workflow a name.");
      return;
    }
    if (steps.length === 0) {
      setError("Add at least one step.");
      return;
    }
    const payloadSteps: ApprovalStepTemplate[] = steps.map((s, i) => ({
      order: i + 1,
      approver_kind: s.approver_kind,
      approver_role: s.approver_kind === "ROLE" ? s.approver_role : null,
      approver_user: s.approver_kind === "NAMED" ? s.approver_user : null,
      required: s.required,
      timeout_hours: s.timeout_hours,
    }));
    try {
      await create.mutateAsync({
        name: name.trim(),
        artifact_type: artifact,
        mode,
        steps: payloadSteps,
      });
      notifySuccess("Workflow created", "Activate it to start routing.");
      onOpenChange(false);
    } catch (err) {
      setError(mapApiError(err).message);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Create approval workflow</DialogTitle>
          <DialogDescription>
            Define ordered approvers. Steps are fixed at creation — to change them later, create a
            new workflow (in-flight routes keep their original steps).
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[60vh] space-y-4 overflow-y-auto scrollbar-thin pr-1">
          {error && (
            <p className="rounded-md bg-danger-subtle px-3 py-2 text-sm text-danger">{error}</p>
          )}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Field label="Name" required className="sm:col-span-1">
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Review sign-off" />
            </Field>
            <Field label="Artifact type" required>
              <Select value={artifact} onValueChange={setArtifact}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {ARTIFACT_TYPES.map((a) => (
                    <SelectItem key={a} value={a}>{a === "review" ? "Review" : "Job Description"}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Mode" required>
              <Select value={mode} onValueChange={(v) => setMode(v as "SEQUENTIAL" | "PARALLEL")}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="SEQUENTIAL">Sequential</SelectItem>
                  <SelectItem value="PARALLEL">Parallel</SelectItem>
                </SelectContent>
              </Select>
            </Field>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Steps</span>
              <Button variant="outline" size="sm" onClick={() => setSteps((s) => [...s, newStep()])}>
                <Plus className="h-4 w-4" /> Add step
              </Button>
            </div>
            <div className="space-y-2">
              {steps.map((step, i) => (
                <div key={i} className="rounded-lg border border-border p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-xs font-semibold text-muted-foreground">Step {i + 1}</span>
                    {steps.length > 1 && (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        className="text-danger"
                        onClick={() => setSteps((s) => s.filter((_, idx) => idx !== i))}
                        aria-label="Remove step"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <Field label="Approver type">
                      <Select
                        value={step.approver_kind}
                        onValueChange={(v) => patchStep(i, { approver_kind: v as "ROLE" | "NAMED" })}
                      >
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="ROLE">By role</SelectItem>
                          <SelectItem value="NAMED">Named person</SelectItem>
                        </SelectContent>
                      </Select>
                    </Field>
                    {step.approver_kind === "ROLE" ? (
                      <Field label="Role">
                        <Select
                          value={step.approver_role}
                          onValueChange={(v) => patchStep(i, { approver_role: v as Role })}
                        >
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {ROLES.map((r) => (
                              <SelectItem key={r} value={r}>{ROLE_LABEL[r]}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </Field>
                    ) : (
                      <Field label="Person">
                        <Select
                          value={step.approver_user ?? ""}
                          onValueChange={(v) => patchStep(i, { approver_user: v })}
                        >
                          <SelectTrigger><SelectValue placeholder="Select…" /></SelectTrigger>
                          <SelectContent>
                            {people.map((p) => (
                              <SelectItem key={p.id} value={p.id}>{p.display}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </Field>
                    )}
                    <Field label="Timeout (hours)">
                      <Input
                        type="number"
                        min={1}
                        value={step.timeout_hours}
                        onChange={(e) => patchStep(i, { timeout_hours: Number(e.target.value) })}
                      />
                    </Field>
                    <div className="flex items-end gap-2 pb-1">
                      <Switch
                        checked={step.required}
                        onCheckedChange={(c) => patchStep(i, { required: c })}
                        id={`req-${i}`}
                      />
                      <label htmlFor={`req-${i}`} className="text-sm text-muted-foreground">
                        Required
                      </label>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} loading={create.isPending}>Create workflow</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
