import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { BarChart3, Target } from "lucide-react";
import { Panel } from "@/components/Panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { StatusBadge } from "@/components/StatusBadge";
import { PersonName } from "@/components/PersonName";
import { LinesSkeleton } from "@/components/Skeletons";
import { goalsApi, cyclesApi, reviewsApi } from "@/lib/api/endpoints";
import { useAuth } from "@/lib/auth/AuthContext";
import { humanize } from "@/lib/enums";
import { formatScore } from "@/lib/format";
import { notifyError, notifySuccess } from "@/lib/toast";
import { useQueryClient } from "@tanstack/react-query";
import type { ReviewAssessment } from "@/lib/types";

/**
 * The evidence panel shown beside the review draft: the subject's goals + KPI
 * attainment and their computed CycleScore (risk). Grounds the manager's review
 * (and any AI draft) in real performance data — the manager isn't writing blind.
 */
export function EvidencePanel({ employee, cycle }: { employee: string; cycle: string }) {
  const goals = useQuery({
    queryKey: ["goals", "evidence", cycle],
    queryFn: () => goalsApi.list({ cycle, page_size: 200 }),
  });
  const scores = useQuery({
    queryKey: ["cycles", "scores", cycle],
    queryFn: () => cyclesApi.scores(cycle),
  });

  const myGoals = (goals.data?.results ?? []).filter((g) => g.employee === employee);
  const score = (scores.data ?? []).find((s) => s.employee === employee);

  return (
    <Panel
      title="Evidence"
      icon={BarChart3}
      aside={score ? <StatusBadge status={score.risk_status} dot /> : undefined}
    >
      {goals.isLoading || scores.isLoading ? (
        <LinesSkeleton lines={4} />
      ) : (
        <div className="space-y-4">
          {score && (
            <div className="flex items-center gap-4 rounded-md bg-secondary/40 px-3 py-2">
              <Metric label="T-score" value={formatScore(score.t_score)} />
              <Metric label="Raw" value={formatScore(score.raw_score)} />
              <Metric label="Cohort" value={String(score.cohort_size)} />
              {score.pace_behind && <Badge variant="warning">Behind pace</Badge>}
            </div>
          )}
          {myGoals.length > 0 ? (
            <ul className="space-y-2.5">
              {myGoals.map((g) => (
                <li key={g.id} className="space-y-1">
                  <div className="flex items-center gap-2 text-sm">
                    <Target className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="font-medium">{g.title}</span>
                    <span className="text-2xs text-muted-foreground">weight {g.weight}</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5 pl-5">
                    {g.kpis.map((k) => (
                      <Badge key={k.id} variant="muted" className="gap-1">
                        {k.name}
                        <span className="text-muted-foreground">
                          {k.latest_actual != null
                            ? `${formatScore(k.latest_actual)}/${formatScore(k.target_value)}`
                            : `target ${formatScore(k.target_value)}`}
                        </span>
                      </Badge>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">No goals recorded for this cycle.</p>
          )}
        </div>
      )}
    </Panel>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-2xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="text-sm font-semibold tabular-nums">{value}</div>
    </div>
  );
}

/**
 * Assessments panel with capture. The reviewer can record a MANAGER assessment;
 * the subject records a SELF assessment. These feed the review (and the AI draft's
 * evidence). Read-only list of all submitted assessments.
 */
export function AssessmentsPanel({
  reviewId,
  reviewerId,
  employeeId,
  assessments,
  loading,
}: {
  reviewId: string;
  reviewerId: string;
  employeeId: string;
  assessments: ReviewAssessment[] | undefined;
  loading: boolean;
}) {
  const { me } = useAuth();
  const qc = useQueryClient();
  const [body, setBody] = React.useState("");
  const [saving, setSaving] = React.useState(false);

  const myType =
    me?.id === reviewerId ? "MANAGER" : me?.id === employeeId ? "SELF" : null;
  // One assessment per (review, assessor): SELF upserts, others are create-once.
  const mineExists = (assessments ?? []).some((a) => a.assessor === me?.id);
  const canCapture = myType === "SELF" || (myType === "MANAGER" && !mineExists);

  async function submit() {
    if (!myType || !body.trim()) return;
    setSaving(true);
    try {
      await reviewsApi.upsertAssessment(reviewId, { assessment_type: myType, body: body.trim() });
      await qc.invalidateQueries({ queryKey: ["reviews", "assessments", reviewId] });
      setBody("");
      notifySuccess("Assessment saved");
    } catch (err) {
      notifyError(err);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Panel title="Assessments">
      {loading ? (
        <LinesSkeleton lines={3} />
      ) : (
        <div className="space-y-3">
          {assessments && assessments.length > 0 ? (
            <ul className="space-y-3">
              {assessments.map((a) => (
                <li key={a.id} className="space-y-1">
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary">{humanize(a.assessment_type)}</Badge>
                    <span className="text-2xs text-muted-foreground">
                      <PersonName id={a.assessor} />
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground">{a.body}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">No assessments submitted yet.</p>
          )}

          {myType && !canCapture && mineExists && (
            <p className="border-t border-border pt-3 text-2xs text-muted-foreground">
              You've submitted your {humanize(myType)} assessment.
            </p>
          )}
          {canCapture && (
            <div className="space-y-2 border-t border-border pt-3">
              <p className="text-2xs font-semibold uppercase tracking-wide text-muted-foreground">
                {myType === "SELF" && mineExists ? "Update your Self assessment" : `Add your ${humanize(myType!)} assessment`}
              </p>
              <Textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder={myType === "SELF" ? "Reflect on your cycle…" : "Your assessment of this report…"}
                className="min-h-20"
              />
              <div className="flex justify-end">
                <Button size="sm" onClick={submit} loading={saving} disabled={!body.trim()}>
                  Save assessment
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}
