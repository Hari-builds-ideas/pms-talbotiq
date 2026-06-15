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
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { LinesSkeleton } from "@/components/Skeletons";
import { ErrorState } from "@/components/ErrorState";
import { StatusBadge } from "@/components/StatusBadge";
import { SourceBadge, HitlBanner, ConfidenceBadge } from "@/components/Hitl";
import { useJd, useJdMutations, useJdVersions } from "./useJd";
import { useAuth } from "@/lib/auth/AuthContext";
import { notifyError, notifySuccess } from "@/lib/toast";
import { mapApiError } from "@/lib/errors";
import type { JdBody } from "@/lib/types";

const EMPTY_BODY: JdBody = { summary: "", responsibilities: [], must_haves: [], nice_to_haves: [] };

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

  // Editor holds raw multiline strings so typing newlines is natural.
  const [summary, setSummary] = React.useState("");
  const [resp, setResp] = React.useState("");
  const [must, setMust] = React.useState("");
  const [nice, setNice] = React.useState("");
  const [aiUnavailable, setAiUnavailable] = React.useState(false);

  const working = versions.data?.[0];

  React.useEffect(() => {
    const b = working?.body ?? EMPTY_BODY;
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

  async function generate() {
    setAiUnavailable(false);
    try {
      await m.generate.mutateAsync();
    } catch (err) {
      if (mapApiError(err).kind === "ai_unavailable") setAiUnavailable(true);
      else notifyError(err);
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
        {aiUnavailable && (
          <Alert variant="ai">
            <Sparkles />
            <AlertTitle>JD generator not configured</AlertTitle>
            <AlertDescription>The AI generator isn't connected for this tenant. Author the JD manually below.</AlertDescription>
          </Alert>
        )}

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
                <BodyView body={working?.body ?? EMPTY_BODY} />
              )}
            </Panel>

            {canAuthor && (
              <ActionBar
                status={j.status}
                hasGenerator={hasFeature("jd_generator")}
                pending={{ submit: m.submit.isPending, approve: m.approve.isPending, revise: m.revise.isPending, archive: m.archive.isPending, generate: m.generate.isPending }}
                onSubmit={() => run(() => m.saveDraft.mutateAsync(currentBody()).then(() => m.submit.mutateAsync()), "Submitted for review")}
                onApprove={() => run(() => m.approve.mutateAsync(), "JD published")}
                onRevise={() => run(() => m.revise.mutateAsync(), "New draft version created")}
                onArchive={() => run(() => m.archive.mutateAsync(), "JD archived")}
                onGenerate={generate}
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
      </div>
    </TooltipProvider>
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
