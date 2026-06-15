import { toast } from "@/components/ui/sonner";
import { errorTitle, mapApiError } from "./errors";

/** Surface an API error as a toast with the right title + detail. */
export function notifyError(err: unknown, fallback?: string): void {
  const mapped = mapApiError(err);
  // 401 is handled by the refresh interceptor / auth guard — stay quiet.
  if (mapped.kind === "unauthenticated") return;
  toast.error(errorTitle(mapped.kind), {
    description: fallback ?? mapped.message,
  });
}

export function notifySuccess(message: string, description?: string): void {
  toast.success(message, description ? { description } : undefined);
}

export function notifyInfo(message: string, description?: string): void {
  toast(message, description ? { description } : undefined);
}

export { toast };
