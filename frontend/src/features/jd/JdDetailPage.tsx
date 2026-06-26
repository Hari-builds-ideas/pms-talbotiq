import * as React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Archive, ArrowLeft, Check, History, Save, Send, Sparkles } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Field } from "@/components/Field";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { LinesSkeleton } from "@/components/Skeletons";
import { ErrorState } from "@/components/ErrorState";
import { StatusBadge } from "@/components/StatusBadge";
import { SourceBadge, HitlBanner, ConfidenceBadge } from "@/components/Hitl";
import { useQueryClient } from "@tanstack/react-query";
import { useJd, useJdMutations, useJdVersions } from "./useJd";
import { useAuth } from "@/lib/auth/AuthContext";
import { notifyError, notifySuccess } from "@/lib/toast";
import { jdApi } from "@/lib/api/endpoints";
import { useAIAction } from "@/lib/hooks/useAIAction";
import { AIJobBanner } from "@/components/AIJobBanner";
import type { JdBody } from "@/lib/types";

/**
 * Coerce a possibly partial/empty/null JD body into a complete JdBody. The backend
 * stores `body` as a JSONField defaulting to `{}` (a manual draft, or a JD before
 * any AI/author body), so `body.responsibilities` can be undefined at runtime even
 * though the type says string[]. Calling `.join`/`.map` on that threw and crashed
 * the whole screen ("This screen hit an unexpected error" — BUG 4). Normalising
 * every field to a safe default makes a bad/empty body degrade gracefully.
 */
export function normalizeBody(body: Partial<JdBody> | null | undefined): JdBody {
  return {
    summary: body?.summary ?? "",
    responsibilities: body?.responsibilities ?? [],
    must_haves: body?.must_haves ?? [],
    nice_to_haves: body?.nice_to_haves ?? [],
  };
}

function toLines(s: string): string[] {
  return s.split("\n").map((x) => x.trim()).filter(Boolean);
}

export function JdDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const jd = useJd(id);
  const versions = useJdVersions(id);
  const { atLeast, hasFeature } = useAuth();
  const m = useJdMutations(id);
  const qc = useQueryClient();

  // The AI generate seam is async: inputs are saved first (sync, 422 if missing),
  // then the job is fired and polled. On SUCCEEDED the JD body is written + the
  // JD is PENDING, so re-fetch. DEGRADED/FAILED surface in the banner.
  const generateAi = useAIAction(() => jdApi.generate(id, {}), {
    onSucceeded: () => {
      void qc.invalidateQueries({ queryKey: ["jd"] });
      notifySuccess("AI draft generated", "Review it below, then submit/approve.");
    },
  });

  // Editor holds raw multiline strings so typing newlines is natural.
  const [summary, setSummary] = React.useState("");
  const [resp, setResp] = React.useState("");
  const [must, setMust] = React.useState("");
  const [nice, setNice] = React.useState("");
  const [genOpen, setGenOpen] = React.useState(false);

  const working = versions.data?.[0];

  React.useEffect(() => {
    const b = normalizeBody(working?.body);
    setSummary(b.summary);
    setResp(b.responsibilities.join("\n"));
    setMust(b.must_haves.join("\n"));
    setNice(b.nice_to_haves.join("\n"));
  }, [working]);

  if (jd.isLoading) {
    return <div className="space-y-4"><BackLink /><LinesSkeleton lines={8} /></div>;
  }
  if (jd.isError) {
    return (
      <div className="space-y-4">
        <BackLink />
        <ErrorState error={jd.error} onRetry={() => jd.refetch()} onBack={() => navigate("/jd")} />
      </div>
    );
  }
  const j = jd.data;
  if (!j) return null;

  const canAuthor = atLeast("HRBP");
  const editable = canAuthor && (j.status === "DRAFT" || j.status === "PENDING_HUMAN_REVIEW");

  function currentBody(): JdBody {
    return {
      summary: summary.trim(),
      responsibilities: toLines(resp),
      must_haves: toLines(must),
      nice_to_haves: toLines(nice),
    };
  }

  async function run(fn: () => Promise<unknown>, msg: string) {
    try {
      await fn();
      notifySuccess(msg);
    } catch (err) {
      notifyError(err);
      void jd.refetch();
    }
  }

  // The generator needs a saved role brief (inputs) first — otherwise it 422s.
  // Collect the brief in a dialog, save it, then generate.
  async function generateWithInputs(brief: Record<string, unknown>) {
    try {
      await m.saveInputs.mutateAsync(brief); // inputs first (else generate 422s)
      setGenOpen(false);
      generateAi.start(); // async: poll the job via the banner below
    } catch (err) {
      notifyError(err);
    }
  }

  return (
    <TooltipProvider delayDuration={200}>
      <div className="space-y-5">
        <BackLink />
        <PageHeader
          eyebrow="Job description"
          title={j.title}
          description={`${j.level}${j.department ? ` · ${j.department}` : ""}`}
          actions={
            <span className="flex items-center gap-2">
              <SourceBadge source={j.source} />
              <StatusBadge status={j.status} dot />
            </span>
          }
        />

        {j.status === "PENDING_HUMAN_REVIEW" && (
          <HitlBanner source={j.source} confidence={working?.confidence_score} message="This JD is pending review. Approve to publish it (or it enters an active approval route)." />
        )}
        {j.status === "IN_REVIEW" && (
          <Alert variant="info">
            <Check />
            <AlertTitle>In an approval route</AlertTitle>
            <AlertDescription>This JD is moving through its approval route and will publish when the route completes.</AlertDescription>
          </Alert>
        )}
        <AIJobBanner job={generateAi.job} working="Generating the JD with AI…" onRetry={generateAi.start} />

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-2">
            <Panel
              title={editable ? "Edit JD body" : "JD body"}
              aside={working?.confidence_score ? <ConfidenceBadge score={working.confidence_score} /> : undefined}
            >
              {versions.isLoading ? (
                <LinesSkeleton lines={6} />
              ) : editable ? (
                <div className="space-y-4">
                  <Field label="Summary">
                    <Textarea value={summary} onChange={(e) => setSummary(e.target.value)} className="min-h-20" />
                  </Field>
                  <Field label="Responsibilities (one per line)">
                    <Textarea value={resp} onChange={(e) => setResp(e.target.value)} className="min-h-20" />
                  </Field>
                  <Field label="Must-haves (one per line)">
                    <Textarea value={must} onChange={(e) => setMust(e.target.value)} className="min-h-20" />
                  </Field>
                  <Field label="Nice-to-haves (one per line)">
                    <Textarea value={nice} onChange={(e) => setNice(e.target.value)} className="min-h-16" />
                  </Field>
                  <div className="flex justify-end">
                    <Button variant="outline" onClick={() => run(() => m.saveDraft.mutateAsync(currentBody()), "Draft saved")} loading={m.saveDraft.isPending}>
                      <Save className="h-4 w-4" /> Save draft
                    </Button>
                  </div>
                </div>
              ) : (
                <BodyView body={normalizeBody(working?.body)} />
              )}
            </Panel>

            {canAuthor && (
              <ActionBar
                status={j.status}
                hasGenerator={hasFeature("jd_generator")}
                pending={{ submit: m.submit.isPending, approve: m.approve.isPending, revise: m.revise.isPending, archive: m.archive.isPending, generate: generateAi.isWorking }}
                onSubmit={() => run(() => m.saveDraft.mutateAsync(currentBody()).then(() => m.submit.mutateAsync()), "Submitted for review")}
                onApprove={() => run(() => m.approve.mutateAsync(), "JD published")}
                onRevise={() => run(() => m.revise.mutateAsync(), "New draft version created")}
                onArchive={() => run(() => m.archive.mutateAsync(), "JD archived")}
                onGenerate={() => setGenOpen(true)}
              />
            )}
          </div>

          <div className="space-y-5">
            <Panel title="Version history" icon={History}>
              {versions.isLoading ? (
                <LinesSkeleton lines={3} />
              ) : versions.data && versions.data.length > 0 ? (
                <ul className="space-y-2">
                  {versions.data.map((v) => (
                    <li key={v.id ?? v.version_number} className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2">
                      <div>
                        <span className="text-sm font-medium">Version {v.version_number}</span>
                        {v.confidence_score && <span className="ml-2 text-2xs text-ai">AI · {Math.round(Number(v.confidence_score) * 100)}%</span>}
                      </div>
                      {v.is_published ? <Badge variant="success">Live</Badge> : <Badge variant="muted">Draft</Badge>}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">No versions.</p>
              )}
            </Panel>
          </div>
        </div>

        <GenerateDialog
          open={genOpen}
          onOpenChange={setGenOpen}
          title={j.title}
          level={j.level}
          loading={m.saveInputs.isPending || m.generate.isPending}
          onGenerate={generateWithInputs}
        />
      </div>
    </TooltipProvider>
  );
}

function GenerateDialog({
  open,
  onOpenChange,
  title,
  level,
  loading,
  onGenerate,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  level: string;
  loading: boolean;
  onGenerate: (brief: Record<string, unknown>) => void;
}) {
  const [summary, setSummary] = React.useState("");
  const [responsibilities, setResponsibilities] = React.useState("");
  const [mustHaves, setMustHaves] = React.useState("");

  React.useEffect(() => {
    if (open) { setSummary(""); setResponsibilities(""); setMustHaves(""); }
  }, [open]);

  const lines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-ai" /> Generate {title} ({level}) with AI
          </DialogTitle>
          <DialogDescription>
            Give the AI a short brief to ground the draft. It's saved as the role inputs, then the
            generator writes a draft you review before publishing (HITL).
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <Field label="Role summary / context" required>
            <Textarea value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="What this role owns and why it exists…" className="min-h-20" />
          </Field>
          <Field label="Key responsibilities (one per line)">
            <Textarea value={responsibilities} onChange={(e) => setResponsibilities(e.target.value)} className="min-h-16" />
          </Field>
          <Field label="Must-haves (one per line)">
            <Textarea value={mustHaves} onChange={(e) => setMustHaves(e.target.value)} className="min-h-16" />
          </Field>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            variant="premium"
            loading={loading}
            disabled={!summary.trim()}
            onClick={() => onGenerate({ summary: summary.trim(), responsibilities: lines(responsibilities), must_haves: lines(mustHaves), level })}
          >
            <Sparkles className="h-4 w-4" /> Generate draft
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function BodyView({ body }: { body: JdBody }) {
  return (
    <div className="space-y-4 text-sm">
      {body.summary ? (
        <p className="leading-relaxed text-foreground">{body.summary}</p>
      ) : (
        <p className="text-muted-foreground">No summary yet.</p>
      )}
      <Section title="Responsibilities" items={body.responsibilities} />
      <Section title="Must-haves" items={body.must_haves} />
      <Section title="Nice-to-haves" items={body.nice_to_haves} />
    </div>
  );
}

function Section({ title, items }: { title: string; items: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div>
      <p className="mb-1 text-2xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</p>
      <ul className="list-disc space-y-0.5 pl-4 text-muted-foreground">
        {items.map((it, i) => (
          <li key={i}>{it}</li>
        ))}
      </ul>
    </div>
  );
}

function ActionBar({
  status,
  hasGenerator,
  pending,
  onSubmit,
  onApprove,
  onRevise,
  onArchive,
  onGenerate,
}: {
  status: string;
  hasGenerator: boolean;
  pending: { submit: boolean; approve: boolean; revise: boolean; archive: boolean; generate: boolean };
  onSubmit: () => void;
  onApprove: () => void;
  onRevise: () => void;
  onArchive: () => void;
  onGenerate: () => void;
}) {
  const archiveBtn = status !== "ARCHIVED" && (
    <Button key="archive" variant="ghost" className="text-danger" onClick={onArchive} loading={pending.archive}>
      <Archive className="h-4 w-4" /> Archive
    </Button>
  );

  const right: React.ReactNode[] = [];

  if (status === "DRAFT") {
    right.push(
      hasGenerator ? (
        <Button key="gen" variant="outline" onClick={onGenerate} loading={pending.generate}>
          <Sparkles className="h-4 w-4 text-ai" /> Generate with AI
        </Button>
      ) : (
        <Tooltip key="gen">
          <TooltipTrigger asChild>
            <span tabIndex={0}><Button variant="outline" disabled><Sparkles className="h-4 w-4" /> Generate with AI</Button></span>
          </TooltipTrigger>
          <TooltipContent>JD generator is a Full AI feature — upgrade to unlock.</TooltipContent>
        </Tooltip>
      ),
      <Button key="submit" onClick={onSubmit} loading={pending.submit}>
        <Send className="h-4 w-4" /> Submit for review
      </Button>,
    );
  } else if (status === "PENDING_HUMAN_REVIEW") {
    right.push(
      <Button key="approve" onClick={onApprove} loading={pending.approve}>
        <Check className="h-4 w-4" /> Approve &amp; publish
      </Button>,
    );
  } else if (status === "PUBLISHED") {
    right.push(
      <Button key="revise" variant="outline" onClick={onRevise} loading={pending.revise}>
        Revise (new version)
      </Button>,
    );
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="flex gap-2">{archiveBtn}</div>
      <div className="flex flex-wrap gap-2">{right}</div>
    </div>
  );
}

function BackLink() {
  return (
    <Link to="/jd" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft className="h-4 w-4" /> Back to JD library
    </Link>
  );
}
