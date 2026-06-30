import * as React from "react";
import {
  Check,
  CreditCard,
  Lock,
  Minus,
  Plus,
  Sparkles,
  Users,
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { StatCard } from "@/components/StatCard";
import { LinesSkeleton, CardGridSkeleton } from "@/components/Skeletons";
import { ErrorState } from "@/components/ErrorState";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  useBillingMutations,
  useEntitlement,
  useFeatureFlags,
  useUpgradePrompt,
} from "./useAdmin";
import { useAuth } from "@/lib/auth/AuthContext";
import { FEATURE_KEYS, FEATURE_META, type FeatureKey } from "@/lib/enums";
import { notifySuccess } from "@/lib/toast";
import { mapApiError } from "@/lib/errors";
import { cn } from "@/lib/utils";

export function BillingPage() {
  const ent = useEntitlement();
  const flags = useFeatureFlags();
  const { refreshFeatures } = useAuth();
  const [upgradeOpen, setUpgradeOpen] = React.useState(false);

  const isFullAi = ent.data?.feature_packs.includes("FULL_AI");

  if (ent.isError) return <ErrorWrap error={ent.error} retry={() => ent.refetch()} />;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Settings" title="Entitlements"
        description="Your plan, seats and feature packs. Upgrading to Full AI unlocks every premium capability instantly — seats are unchanged."
        actions={
          !isFullAi ? (
            <Button variant="premium" onClick={() => setUpgradeOpen(true)}>
              <Sparkles className="h-4 w-4" />
              Upgrade to Full AI
            </Button>
          ) : (
            <Badge variant="success" className="gap-1 px-3 py-1.5">
              <Check className="h-3.5 w-3.5" /> Full AI active
            </Badge>
          )
        }
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard
          label="Current plan"
          value={ent.data?.tier_label ?? "—"}
          icon={CreditCard}
          tone={isFullAi ? "success" : "info"}
          loading={ent.isLoading}
          hint={ent.data ? ent.data.feature_packs.join(" + ") : undefined}
        />
        <StatCard
          label="Seats"
          value={ent.data?.seat_count ?? "—"}
          icon={Users}
          loading={ent.isLoading}
          hint="Independent of feature packs"
        />
        <StatCard
          label="Unlocked features"
          value={
            flags.data
              ? `${Object.values(flags.data).filter(Boolean).length} / ${FEATURE_KEYS.length}`
              : "—"
          }
          icon={Sparkles}
          tone="ai"
          loading={flags.isLoading}
        />
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <FeatureMatrix
            flags={flags.data}
            loading={flags.isLoading}
            error={flags.isError ? flags.error : null}
            onRetry={() => flags.refetch()}
            onUpgrade={() => setUpgradeOpen(true)}
            isFullAi={Boolean(isFullAi)}
          />
        </div>
        <SeatsPanel
          seats={ent.data?.seat_count}
          loading={ent.isLoading}
        />
      </div>

      <UpgradeModal
        open={upgradeOpen}
        onOpenChange={setUpgradeOpen}
        onUpgraded={refreshFeatures}
      />
    </div>
  );
}

function FeatureMatrix({
  flags,
  loading,
  error,
  onRetry,
  onUpgrade,
  isFullAi,
}: {
  flags?: Record<string, boolean>;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  onUpgrade: () => void;
  isFullAi: boolean;
}) {
  return (
    <Panel title="Feature map" icon={Sparkles}>
      {loading ? (
        <LinesSkeleton lines={6} />
      ) : error ? (
        <ErrorState error={error} onRetry={onRetry} compact />
      ) : (
        <ul className="divide-y divide-border">
          {FEATURE_KEYS.map((key) => {
            const meta = FEATURE_META[key];
            const unlocked = Boolean(flags?.[key]);
            return (
              <li key={key} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
                <div className="flex min-w-0 items-center gap-3">
                  <div
                    className={cn(
                      "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
                      unlocked ? "bg-success-subtle text-success" : "bg-muted text-muted-foreground",
                    )}
                  >
                    {unlocked ? <Check className="h-4 w-4" /> : <Lock className="h-4 w-4" />}
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium">{meta.label}</span>
                      <Badge variant={meta.pack === "STARTER" ? "secondary" : "premium"}>
                        {meta.pack === "STARTER" ? "Starter" : "Full AI"}
                      </Badge>
                    </div>
                    <p className="truncate text-2xs text-muted-foreground">{meta.description}</p>
                  </div>
                </div>
                {unlocked ? (
                  <Badge variant="success">Unlocked</Badge>
                ) : isFullAi ? (
                  <Badge variant="muted">Off</Badge>
                ) : (
                  <Button variant="ghost" size="sm" className="text-premium" onClick={onUpgrade}>
                    Unlock
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

function SeatsPanel({ seats, loading }: { seats?: number; loading: boolean }) {
  const { setSeats } = useBillingMutations();
  const [value, setValue] = React.useState<number>(seats ?? 0);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (seats != null) setValue(seats);
  }, [seats]);

  const dirty = seats != null && value !== seats;

  async function save() {
    setError(null);
    if (!Number.isInteger(value) || value < 0) {
      setError("Seats must be a non-negative whole number.");
      return;
    }
    try {
      await setSeats.mutateAsync(value);
      notifySuccess("Seat count updated");
    } catch (err) {
      setError(mapApiError(err).message);
    }
  }

  return (
    <Panel title="Seats" icon={Users}>
      {loading ? (
        <LinesSkeleton lines={3} />
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Seats are billed independently of feature packs.
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon"
              onClick={() => setValue((v) => Math.max(0, v - 1))}
              aria-label="Decrease seats"
            >
              <Minus className="h-4 w-4" />
            </Button>
            <Input
              type="number"
              min={0}
              value={value}
              onChange={(e) => setValue(Number(e.target.value))}
              className="w-24 text-center tabular-nums"
            />
            <Button
              variant="outline"
              size="icon"
              onClick={() => setValue((v) => v + 1)}
              aria-label="Increase seats"
            >
              <Plus className="h-4 w-4" />
            </Button>
          </div>
          {error && <p className="text-xs text-danger">{error}</p>}
          <Button onClick={save} loading={setSeats.isPending} disabled={!dirty} className="w-full">
            Save seats
          </Button>
        </div>
      )}
    </Panel>
  );
}

function UpgradeModal({
  open,
  onOpenChange,
  onUpgraded,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onUpgraded: () => Promise<void>;
}) {
  const prompt = useUpgradePrompt();
  const { upgrade } = useBillingMutations();

  async function doUpgrade() {
    await upgrade.mutateAsync();
    await onUpgraded();
    notifySuccess("Upgraded to Full AI", "Every premium feature is now unlocked.");
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-premium" />
            Upgrade to Full AI
          </DialogTitle>
          <DialogDescription>
            Conceptual upgrade — no pricing or payment is captured. Premium flags
            flip on instantly across the workspace.
          </DialogDescription>
        </DialogHeader>

        {prompt.isLoading ? (
          <CardGridSkeleton count={2} />
        ) : prompt.isError ? (
          <ErrorState error={prompt.error} onRetry={() => prompt.refetch()} compact />
        ) : prompt.data ? (
          <div className="space-y-3">
            <p className="text-2xs font-semibold uppercase tracking-wide text-muted-foreground">
              You'll unlock
            </p>
            <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {prompt.data.upgrade.would_unlock.map((k) => {
                const meta = FEATURE_META[k as FeatureKey];
                return (
                  <li key={k} className="flex items-start gap-2 rounded-md border border-border p-2.5">
                    <div className="mt-0.5 flex h-5 w-5 items-center justify-center rounded bg-premium-subtle text-premium">
                      <Sparkles className="h-3 w-3" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{meta?.label ?? k}</p>
                      <p className="text-2xs text-muted-foreground">{meta?.description}</p>
                    </div>
                  </li>
                );
              })}
            </ul>
            <p className="rounded-md bg-secondary/60 px-3 py-2 text-2xs text-muted-foreground">
              {prompt.data.upgrade.note}
            </p>
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Not now</Button>
          <Button variant="premium" onClick={doUpgrade} loading={upgrade.isPending}>
            <Sparkles className="h-4 w-4" />
            Confirm upgrade
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ErrorWrap({ error, retry }: { error: unknown; retry: () => void }) {
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Settings" title="Entitlements" />
      <ErrorState error={error} onRetry={retry} />
    </div>
  );
}
