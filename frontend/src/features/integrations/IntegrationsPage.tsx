import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Plug, ShieldAlert } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Field } from "@/components/Field";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { CardGridSkeleton } from "@/components/Skeletons";
import { ErrorState } from "@/components/ErrorState";
import { integrationsApi } from "@/lib/api/endpoints";
import { INTEGRATION_KIND, type IntegrationKind } from "@/lib/enums";
import { notifyError, notifySuccess } from "@/lib/toast";
import type { TenantIntegration } from "@/lib/types";

const CONFIG_FIELDS: Record<IntegrationKind, { key: string; label: string; placeholder: string }[]> = {
  JIRA: [
    { key: "base_url", label: "Base URL", placeholder: "https://acme.atlassian.net" },
    { key: "email", label: "Bot email", placeholder: "bot@acme.test" },
    { key: "project", label: "Project key", placeholder: "PERF" },
    { key: "value_field", label: "Value field", placeholder: "customfield_actual" },
  ],
  SLACK: [{ key: "channel", label: "Channel", placeholder: "#perf-ops" }],
};

export function IntegrationsPage() {
  const q = useQuery({ queryKey: ["integrations"], queryFn: integrationsApi.list });

  return (
    <div>
      <PageHeader
        title="Integrations"
        description="Connect Jira and Slack. Secrets are managed out-of-band — you provide the NAME of an environment variable, never the token itself."
      />

      <Alert variant="info" className="mb-5">
        <ShieldAlert />
        <AlertTitle>Secrets are never stored here</AlertTitle>
        <AlertDescription>
          Enter the env-var name that holds the token (e.g. <code className="font-mono">JIRA_TOKEN_ACME</code>). The raw
          token lives in your secrets manager and is never sent to or returned from the app.
        </AlertDescription>
      </Alert>

      {q.isLoading ? (
        <CardGridSkeleton count={2} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          {INTEGRATION_KIND.map((kind) => (
            <IntegrationCard
              key={kind}
              kind={kind}
              existing={q.data?.find((i) => i.kind === kind) ?? null}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function IntegrationCard({
  kind,
  existing,
}: {
  kind: IntegrationKind;
  existing: TenantIntegration | null;
}) {
  const qc = useQueryClient();
  const [enabled, setEnabled] = React.useState(existing?.enabled ?? false);
  const [config, setConfig] = React.useState<Record<string, string>>(
    () => normaliseConfig(kind, existing?.config),
  );
  const [secretRef, setSecretRef] = React.useState(existing?.secret_ref ?? "");

  React.useEffect(() => {
    setEnabled(existing?.enabled ?? false);
    setConfig(normaliseConfig(kind, existing?.config));
    setSecretRef(existing?.secret_ref ?? "");
  }, [existing, kind]);

  const save = useMutation({
    mutationFn: () =>
      integrationsApi.save(kind, { enabled, config, secret_ref: secretRef.trim() }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["integrations"] });
      notifySuccess(`${kind} integration saved`);
    },
    onError: (err) => notifyError(err),
  });

  return (
    <Panel
      title={kind === "JIRA" ? "Jira" : "Slack"}
      icon={Plug}
      aside={
        existing ? (
          <Badge variant={enabled ? "success" : "muted"}>{enabled ? "Enabled" : "Disabled"}</Badge>
        ) : (
          <Badge variant="muted">Not configured</Badge>
        )
      }
    >
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">Enabled</span>
          <Switch checked={enabled} onCheckedChange={setEnabled} aria-label={`Enable ${kind}`} />
        </div>

        {CONFIG_FIELDS[kind].map((f) => (
          <Field key={f.key} label={f.label}>
            <Input
              value={config[f.key] ?? ""}
              placeholder={f.placeholder}
              onChange={(e) => setConfig((c) => ({ ...c, [f.key]: e.target.value }))}
            />
          </Field>
        ))}

        <Field
          label={
            <span className="flex items-center gap-1.5">
              <KeyRound className="h-3.5 w-3.5" /> Secret env-var name
            </span>
          }
          hint="The NAME of the env var holding the token — not the token value."
        >
          <Input
            value={secretRef}
            placeholder={kind === "JIRA" ? "JIRA_TOKEN_ACME" : "SLACK_WEBHOOK_ACME"}
            onChange={(e) => setSecretRef(e.target.value)}
            className="font-mono text-xs"
          />
        </Field>

        <div className="flex justify-end">
          <Button onClick={() => save.mutate()} loading={save.isPending}>Save {kind === "JIRA" ? "Jira" : "Slack"}</Button>
        </div>
      </div>
    </Panel>
  );
}

function normaliseConfig(
  kind: IntegrationKind,
  config?: Record<string, unknown>,
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const f of CONFIG_FIELDS[kind]) {
    const v = config?.[f.key];
    out[f.key] = typeof v === "string" ? v : "";
  }
  return out;
}
