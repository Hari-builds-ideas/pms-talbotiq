import * as React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Check,
  Clock,
  Loader2,
  Pencil,
  Save,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { LinesSkeleton } from "@/components/Skeletons";
import { ErrorState } from "@/components/ErrorState";
import { StatusBadge } from "@/components/StatusBadge";
import { PersonName } from "@/components/PersonName";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Timeline, type TimelineItem } from "@/components/Stepper";
import { HitlBanner, SourceBadge, ConfidenceBadge } from "@/components/Hitl";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { ReviewStepper } from "./ReviewStepper";
import { AssessmentsPanel, EvidencePanel } from "./ReviewEvidence";
import { CommentsPanel } from "./CommentsPanel";
import { ReviewQualityCheck } from "./ReviewQualityCheck";
import {
  useReview,
  useReviewAssessments,
  useReviewTimeline,
  useReviewTransitions,
} from "./useReviews";
import { useRoute } from "@/features/approvals/useApprovals";
import { RouteTracker } from "@/features/approvals/RouteTracker";
import { useAuth } from "@/lib/auth/AuthContext";
import { humanize } from "@/lib/enums";
import { formatDateTime } from "@/lib/format";
import { notifyError, notifySuccess } from "@/lib/toast";
import { useCycles } from "@/lib/hooks/useCycles";
import { useAIAction } from "@/lib/hooks/useAIAction";
import { AIJobBanner } from "@/components/AIJobBanner";
import { reviewsApi } from "@/lib/api/endpoints";

export function ReviewDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const review = useReview(id);
  const r = review.data;

  if (review.isLoading) {
    return (
      <div className="space-y-4">
        <BackLink />
        <LinesSkeleton lines={8} />
      </div>
    );
  }
  if (review.isError) {
    return (
      <div className="space-y-4">
        <BackLink />
        <ErrorState error={review.error} onRetry={() => review.refetch()} onBack={() => navigate("/reviews")} />
      </div>
    );
  }
  if (!r) return null;

  return <ReviewDetail key={r.id} reviewId={r.id} />;
}

function ReviewDetail({ reviewId }: { reviewId: string }) {
  const { hasFeature, can } = useAuth();
  const { nameOf: cycleName } = useCycles();
  const review = useReview(reviewId);
  const timeline = useReviewTimeline(reviewId);
  const assessments = useReviewAssessments(reviewId);
  const t = useReviewTransitions(reviewId);

  const r = review.data!;
  const route = useRoute(r.approval_route);

  const [body, setBody] = React.useState(r.draft_body);
  const [rejectOpen, setRejectOpen] = React.useState(false);
  // The Agent-1 draft is async: fire → poll the AI job → on SUCCEEDED the review
  // is PENDING, so re-fetch it (and the timeline). DEGRADED/FAILED surface in the
  // banner; the manual path is always available.
  const ai = useAIAction(() => reviewsApi.requestAiDraft(reviewId), {
    onSucceeded: () => {
      void review.refetch();
      void timeline.refetch();
    },
  });

  // Keep the editor in sync when entering EDITING / when the draft changes.
  React.useEffect(() => {
    setBody(r.draft_body);
  }, [r.draft_body, r.state]);

  // D2: the editor + every transition control are capability-gated off the
  // server-provided grants on /me (the SAME matrix the API enforces) — a role
  // that can't perform an action never sees its button. An employee viewing
  // their own review gets a clean read-only page, not 403 walls.
  const canManage = can("manage_reviews");
  const isEditing = r.state === "EDITING" && canManage;
  const isPending = r.state === "PENDING_HUMAN_REVIEW";
  const isDrafting = r.state === "AI_DRAFTING";
  const isFinalized = r.state === "FINALIZED";
  const isRejected = r.state === "REJECTED";

  async function run(fn: () => Promise<unknown>, msg: string) {
    try {
      await fn();
      notifySuccess(msg);
    } catch (err) {
      notifyError(err);
      void review.refetch();
    }
  }

  const displayBody = isFinalized ? r.final_body : r.final_body || r.draft_body;

  return (
    <TooltipProvider delayDuration={200}>
      <div className="space-y-5">
        <BackLink />
        <PageHeader
          eyebrow="Performance review"
          title={<PersonNameTitle id={r.employee} name={r.employee_name} />}
          description={
            <span className="flex flex-wrap items-center gap-2">
              <span>Reviewer: <PersonName id={r.reviewer} name={r.reviewer_name} /></span>
              <span>·</span>
              <span>{r.cycle_name ?? cycleName(r.cycle)}</span>
            </span>
          }
          actions={
            <span className="flex items-center gap-2">
              <SourceBadge source={r.source} />
              <StatusBadge status={r.state} dot />
            </span>
          }
        />

        {isPending && <HitlBanner source={r.source} confidence={r.confidence_score} />}
        {/* Active AI draft job (this session): working / unavailable / failed. */}
        {ai.job ? (
          <AIJobBanner job={ai.job} working="AI is drafting this review…" onRetry={ai.start} />
        ) : (
          isDrafting && (
            <Alert variant="ai">
              <Loader2 className="animate-spin" />
              <AlertTitle>AI is drafting this review…</AlertTitle>
              <AlertDescription>This page will update automatically when the draft is ready.</AlertDescription>
            </Alert>
          )
        )}
        {isRejected && r.rejected_reason && (
          <Alert variant="danger">
            <X />
            <AlertTitle>Rejected</AlertTitle>
            <AlertDescription>{r.rejected_reason}</AlertDescription>
          </Alert>
        )}

        <Card>
          <CardContent className="p-5">
            <ReviewStepper state={r.state} />
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
          {/* Body / editor */}
          <div className="space-y-4 lg:col-span-2">
            <Panel
              title={isEditing ? "Edit review" : "Review"}
              aside={
                r.source === "AI" && r.confidence_score ? (
                  <ConfidenceBadge score={r.confidence_score} />
                ) : undefined
              }
            >
              {isEditing ? (
                <div className="space-y-3">
                  <Textarea
                    value={body}
                    onChange={(e) => setBody(e.target.value)}
                    placeholder="Write the review narrative…"
                    className="min-h-56"
                  />
                  {/* Advisory AI quality/bias check — same capability as the endpoint. */}
                  {canManage && <ReviewQualityCheck text={body} />}
                  <div className="flex justify-end gap-2">
                    <Button
                      variant="outline"
                      onClick={() => run(() => t.saveDraft.mutateAsync(body), "Draft saved")}
                      loading={t.saveDraft.isPending}
                    >
                      <Save className="h-4 w-4" /> Save draft
                    </Button>
                    <Button
                      onClick={() => run(() => t.submit.mutateAsync(body), "Submitted for review")}
                      loading={t.submit.isPending}
                      disabled={!body.trim()}
                    >
                      <Send className="h-4 w-4" /> Submit for review
                    </Button>
                  </div>
                </div>
              ) : displayBody ? (
                <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-foreground">{displayBody}</p>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No content yet. {r.state === "DRAFT" ? "Start editing or request an AI draft." : ""}
                </p>
              )}
            </Panel>

            {/* State-driven action bar — every button capability-gated (D2). */}
            <ActionBar
              state={r.state}
              hasAgent1={hasFeature("agent1")}
              caps={{
                manage: canManage,
                approve: can("approve_review"),
                finalize: can("finalize_review"),
                aiDraft: can("run_ai_review_draft"),
              }}
              pending={{
                startEdit: t.startEdit.isPending,
                approve: t.approve.isPending,
                finalize: t.finalize.isPending,
                ai: ai.isWorking,
              }}
              onStartEdit={() => run(() => t.startEdit.mutateAsync(), "Editing")}
              onApprove={() => run(() => t.approve.mutateAsync(), "Review approved")}
              onReject={() => setRejectOpen(true)}
              onFinalize={() => run(() => t.finalize.mutateAsync(), "Review finalized")}
              onRequestAi={ai.start}
            />

            {/* Evidence the review (and any AI draft) is grounded in. */}
            <EvidencePanel employee={r.employee} cycle={r.cycle} />
          </div>

          {/* Sidebar */}
          <div className="space-y-5">
            <Panel title="Details">
              <dl className="space-y-2.5 text-sm">
                <Row label="Employee"><PersonName id={r.employee} name={r.employee_name} /></Row>
                <Row label="Reviewer"><PersonName id={r.reviewer} name={r.reviewer_name} /></Row>
                <Row label="Cycle">{r.cycle_name ?? cycleName(r.cycle)}</Row>
                <Row label="Human reviewer">
                  {r.human_reviewer ? <PersonName id={r.human_reviewer} name={r.human_reviewer_name} /> : <span className="text-muted-foreground">— not yet approved</span>}
                </Row>
                {r.approved_at && <Row label="Approved">{formatDateTime(r.approved_at)}</Row>}
                {r.finalized_at && <Row label="Finalized">{formatDateTime(r.finalized_at)}</Row>}
              </dl>
            </Panel>

            {r.approval_route && route.data && (
              <Panel title="Approval route">
                <RouteTracker route={route.data} />
              </Panel>
            )}

            <AssessmentsPanel
              reviewId={r.id}
              reviewerId={r.reviewer}
              employeeId={r.employee}
              assessments={assessments.data}
              loading={assessments.isLoading}
            />

            <CommentsPanel reviewId={r.id} />

            <Panel title="History">
              {timeline.isLoading ? (
                <LinesSkeleton lines={3} />
              ) : timeline.data && timeline.data.length > 0 ? (
                <Timeline items={timeline.data.map(transitionToItem)} />
              ) : (
                <p className="text-sm text-muted-foreground">No transitions yet.</p>
              )}
            </Panel>
          </div>
        </div>

        <ConfirmDialog
          open={rejectOpen}
          onOpenChange={setRejectOpen}
          title="Reject this review?"
          description="The review returns to the author for revision."
          confirmLabel="Reject"
          destructive
          reason={{ label: "Reason", placeholder: "Explain what needs to change…", required: true }}
          onConfirm={async (reason) => {
            await t.reject.mutateAsync(reason ?? "");
            notifySuccess("Review rejected");
          }}
        />
      </div>
    </TooltipProvider>
  );
}

/** Which review actions are visible for a state given the caller's server-provided
 *  capability grants. Pure + exported for tests. Mirrors the server exactly:
 *  start-edit/submit → manage_reviews · approve/reject → approve_review ·
 *  finalize → finalize_review · AI draft → run_ai_review_draft. A caller with no
 *  grants gets an empty list (clean read-only page — no 403 walls). */
export function visibleReviewActions(
  state: string,
  caps: { manage: boolean; approve: boolean; finalize: boolean; aiDraft: boolean },
): string[] {
  const out: string[] = [];
  if (state === "DRAFT") {
    if (caps.aiDraft) out.push("ai");
    if (caps.manage) out.push("start-edit");
  } else if (state === "PENDING_HUMAN_REVIEW") {
    if (caps.manage) out.push("edit");
    if (caps.approve) out.push("reject", "approve");
  } else if (state === "APPROVED") {
    if (caps.finalize) out.push("finalize");
  } else if (state === "REJECTED") {
    if (caps.manage) out.push("revise");
  }
  return out;
}

function ActionBar({
  state,
  hasAgent1,
  caps,
  pending,
  onStartEdit,
  onApprove,
  onReject,
  onFinalize,
  onRequestAi,
}: {
  state: string;
  hasAgent1: boolean;
  caps: { manage: boolean; approve: boolean; finalize: boolean; aiDraft: boolean };
  pending: { startEdit: boolean; approve: boolean; finalize: boolean; ai: boolean };
  onStartEdit: () => void;
  onApprove: () => void;
  onReject: () => void;
  onFinalize: () => void;
  onRequestAi: () => void;
}) {
  if (state === "FINALIZED") {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-success/30 bg-success-subtle px-4 py-3 text-sm text-success">
        <Check className="h-4 w-4" />
        Finalized — this review is final and read-only.
      </div>
    );
  }

  const visible = visibleReviewActions(state, caps);
  const buttons: React.ReactNode[] = [];

  if (visible.includes("ai")) {
    buttons.push(
      hasAgent1 ? (
        <Button key="ai" variant="outline" onClick={onRequestAi} loading={pending.ai}>
          <Sparkles className="h-4 w-4 text-ai" /> Request AI draft
        </Button>
      ) : (
        <Tooltip key="ai">
          <TooltipTrigger asChild>
            <span tabIndex={0}>
              <Button variant="outline" disabled>
                <Sparkles className="h-4 w-4" /> Request AI draft
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>Review Assistant is a Full AI feature — upgrade to unlock.</TooltipContent>
        </Tooltip>
      ),
    );
  }
  if (visible.includes("start-edit")) {
    buttons.push(
      <Button key="edit" onClick={onStartEdit} loading={pending.startEdit}>
        <Pencil className="h-4 w-4" /> Start editing
      </Button>,
    );
  }
  if (visible.includes("edit")) {
    buttons.push(
      <Button key="edit" variant="outline" onClick={onStartEdit} loading={pending.startEdit}>
        <Pencil className="h-4 w-4" /> Edit
      </Button>,
    );
  }
  if (visible.includes("reject")) {
    buttons.push(
      <Button key="reject" variant="outline" className="text-danger" onClick={onReject}>
        <X className="h-4 w-4" /> Reject
      </Button>,
    );
  }
  if (visible.includes("approve")) {
    buttons.push(
      <Button key="approve" onClick={onApprove} loading={pending.approve}>
        <Check className="h-4 w-4" /> Approve
      </Button>,
    );
  }
  if (visible.includes("finalize")) {
    buttons.push(
      <Button key="finalize" onClick={onFinalize} loading={pending.finalize}>
        <Check className="h-4 w-4" /> Finalize
      </Button>,
    );
  }
  if (visible.includes("revise")) {
    buttons.push(
      <Button key="edit" onClick={onStartEdit} loading={pending.startEdit}>
        <Pencil className="h-4 w-4" /> Revise
      </Button>,
    );
  }

  if (buttons.length === 0) return null;
  return <div className="flex flex-wrap items-center justify-end gap-2">{buttons}</div>;
}

function transitionToItem(tr: {
  from_state: string;
  to_state: string;
  note?: string;
  actor: string | null;
  actor_name?: string | null;
  at: string;
}): TimelineItem {
  const tone =
    tr.to_state === "APPROVED" || tr.to_state === "FINALIZED"
      ? "success"
      : tr.to_state === "REJECTED"
        ? "danger"
        : "info";
  return {
    key: `${tr.to_state}-${tr.at}`,
    icon: <Clock />,
    tone,
    title: (
      <span>
        {humanize(tr.from_state)} → {humanize(tr.to_state)}
      </span>
    ),
    meta: formatDateTime(tr.at),
    body: (
      <span className="text-xs">
        {tr.actor ? <PersonName id={tr.actor} name={tr.actor_name} /> : "System"}
        {tr.note ? ` · ${tr.note}` : ""}
      </span>
    ),
  };
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right font-medium">{children}</dd>
    </div>
  );
}

function PersonNameTitle({ id, name }: { id: string; name?: string | null }) {
  return <PersonName id={id} name={name} />;
}

function BackLink() {
  return (
    <Link to="/reviews" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft className="h-4 w-4" /> Back to reviews
    </Link>
  );
}
