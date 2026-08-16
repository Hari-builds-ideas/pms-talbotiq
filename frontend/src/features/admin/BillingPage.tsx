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
import { notifyError, notifySuccess } from "@/lib/toast";
import { billingApi } from "@/lib/api/endpoints";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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

      {/* PHASE2 L1.4 — the internal subscription (plan + lifecycle; no gateway). */}
      <SubscriptionCard onChanged={() => void refreshFeatures()} />

      {/* PROD_C — plans + payment (test mode) + invoices. */}
      <PlansAndInvoices onChanged={() => void refreshFeatures()} />

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

/** Plan picker + billing history (PROD_C). With payments off, choosing a plan
 *  flips it immediately (marked "no payment"). With payments on + a paid plan,
 *  the server returns a hosted checkout URL and we redirect; the plan activates
 *  only after the verified webhook — the frontend never marks anything paid. */
const PLAN_ORDER = ["STARTER", "PROFESSIONAL", "ENTERPRISE"] as const;

function money(minor: number, currency: string): string {
  if (!minor) return "Free";
  const major = (minor / 100).toLocaleString(undefined, {
    style: "currency",
    currency: currency || "USD",
    maximumFractionDigits: 0,
  });
  return major;
}

function PlansAndInvoices({ onChanged }: { onChanged: () => void }) {
  const qc = useQueryClient();
  const [cycle, setCycle] = React.useState<"MONTHLY" | "ANNUAL">("MONTHLY");
  const cfg = useQuery({ queryKey: ["billing", "payments-config"], queryFn: billingApi.paymentsConfig });
  const invoices = useQuery({ queryKey: ["billing", "invoices"], queryFn: billingApi.invoices });

  const checkout = useMutation({
    mutationFn: (plan: string) => billingApi.checkout({ plan, cycle }),
    onSuccess: (r) => {
      if (r.status === "pending" && r.checkout_url) {
        // Redirect to the provider's hosted page; activation happens on webhook.
        window.location.href = r.checkout_url;
        return;
      }
      notifySuccess(
        "Plan updated",
        r.paid ? "Payment confirmed." : "Applied (no payment — test/free plan).",
      );
      void qc.invalidateQueries({ queryKey: ["billing"] });
      onChanged();
    },
    onError: (e: unknown) => notifyError(e),
  });

  const prices = cfg.data?.prices;
  const currency = "USD";

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
      <div className="lg:col-span-2">
        <Panel
          title="Plans"
          aside={
            <div className="flex gap-1 rounded-lg border border-border p-0.5 text-xs">
              {(["MONTHLY", "ANNUAL"] as const).map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setCycle(c)}
                  className={cn(
                    "rounded-md px-2.5 py-1 font-medium capitalize",
                    cycle === c ? "bg-primary text-primary-foreground" : "text-muted-foreground",
                  )}
                >
                  {c.toLowerCase()}
                </button>
              ))}
            </div>
          }
        >
          <p className="mb-3 text-xs text-muted-foreground">
            {cfg.data?.payments_enabled
              ? "Paid plans require checkout; the plan activates after payment is confirmed."
              : "Payments are off (test/QA) — choosing a plan applies it immediately."}
          </p>
          {cfg.isLoading ? (
            <CardGridSkeleton count={3} />
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {PLAN_ORDER.map((plan) => {
                const amount = prices?.[plan]?.[cycle]?.[currency] ?? 0;
                return (
                  <div key={plan} className="flex flex-col rounded-xl border border-border p-4">
                    <div className="text-sm font-semibold">{plan[0] + plan.slice(1).toLowerCase()}</div>
                    <div className="mt-1 text-2xl font-bold">
                      {money(amount, currency)}
                      {amount > 0 && (
                        <span className="text-xs font-normal text-muted-foreground">
                          /{cycle === "MONTHLY" ? "mo" : "yr"}
                        </span>
                      )}
                    </div>
                    <Button
                      className="mt-4 w-full"
                      variant="outline"
                      loading={checkout.isPending && checkout.variables === plan}
                      onClick={() => checkout.mutate(plan)}
                    >
                      {amount > 0 ? "Choose plan" : "Select"}
                    </Button>
                  </div>
                );
              })}
            </div>
          )}
        </Panel>
      </div>

      <Panel title="Billing history">
        <p className="mb-3 text-xs text-muted-foreground">Invoices for confirmed payments.</p>
        {invoices.isLoading ? (
          <LinesSkeleton lines={3} />
        ) : !invoices.data || invoices.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">No invoices yet.</p>
        ) : (
          <ul className="max-h-72 space-y-2 overflow-y-auto scrollbar-thin">
            {invoices.data.map((inv) => (
              <li key={inv.id} className="flex items-center justify-between text-sm">
                <span className="font-medium">{inv.number}</span>
                <span className="text-muted-foreground">{money(inv.total, inv.currency)}</span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
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
              inputMode="numeric"
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

/** PHASE2 L1.4 — plan picker + lifecycle status (internal, admin-driven). */
function SubscriptionCard({ onChanged }: { onChanged: () => void }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["billing", "subscription"], queryFn: billingApi.subscription });
  const update = useMutation({
    mutationFn: (body: { plan?: string; status?: string }) => billingApi.subscriptionUpdate(body),
    onSuccess: () => {
      notifySuccess("Subscription updated", "Feature access changed immediately.");
      void qc.invalidateQueries({ queryKey: ["billing"] });
      onChanged();
    },
    onError: (e: unknown) => notifyError(e),
  });
  const s = q.data;
  return (
    <Panel title="Subscription">
      {q.isLoading || !s ? (
        <LinesSkeleton lines={3} />
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-sm text-muted-foreground">Plan</span>
            {Object.entries(s.plans).map(([code, meta]) => (
              <Button
                key={code}
                size="sm"
                variant={s.plan === code ? "default" : "outline"}
                onClick={() => code !== s.plan && update.mutate({ plan: code })}
                loading={update.isPending && update.variables?.plan === code}
              >
                {meta.label}
              </Button>
            ))}
            <Badge variant={s.features_active ? "success" : "danger"} className="ml-auto">
              {s.status}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            {s.employee_limit
              ? `Up to ${s.employee_limit} employees on this plan.`
              : "Unlimited employees on this plan."}{" "}
            Plan features: {s.plan_features.length ? s.plan_features.join(", ") : "AI packs only"}.
            Status changes (trial/past-due/grace/cancel) follow the internal lifecycle — payments
            arrive in a later, human-reviewed build.
          </p>
        </div>
      )}
    </Panel>
  );
}
