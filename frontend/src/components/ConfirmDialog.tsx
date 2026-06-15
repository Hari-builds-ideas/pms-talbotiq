import * as React from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  /** When set, requires a non-empty reason; passed to onConfirm. */
  reason?: {
    label: string;
    placeholder?: string;
    required?: boolean;
  };
  /** Resolve to keep open on error; the dialog closes on success. */
  onConfirm: (reason?: string) => Promise<void> | void;
}

/**
 * Shared confirmation dialog. Supports a required-reason capture (e.g. the
 * review/approval reject flow → 422 REJECTION_REASON_REQUIRED is impossible
 * because we enforce it client-side first).
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive,
  reason,
  onConfirm,
}: ConfirmDialogProps) {
  const [value, setValue] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [touched, setTouched] = React.useState(false);

  React.useEffect(() => {
    if (open) {
      setValue("");
      setTouched(false);
      setLoading(false);
    }
  }, [open]);

  const reasonRequired = reason?.required ?? Boolean(reason);
  const reasonInvalid = reasonRequired && value.trim().length === 0;

  async function handleConfirm() {
    if (reasonInvalid) {
      setTouched(true);
      return;
    }
    try {
      setLoading(true);
      await onConfirm(reason ? value.trim() : undefined);
      onOpenChange(false);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !loading && onOpenChange(o)}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>

        {reason && (
          <div className="space-y-1.5">
            <Label htmlFor="confirm-reason">
              {reason.label}
              {reasonRequired && <span className="text-danger"> *</span>}
            </Label>
            <Textarea
              id="confirm-reason"
              value={value}
              placeholder={reason.placeholder}
              onChange={(e) => setValue(e.target.value)}
              onBlur={() => setTouched(true)}
              aria-invalid={touched && reasonInvalid}
            />
            {touched && reasonInvalid && (
              <p className="text-xs text-danger">A reason is required.</p>
            )}
          </div>
        )}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={loading}
          >
            {cancelLabel}
          </Button>
          <Button
            variant={destructive ? "destructive" : "default"}
            onClick={handleConfirm}
            loading={loading}
            disabled={reasonInvalid && touched}
          >
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
