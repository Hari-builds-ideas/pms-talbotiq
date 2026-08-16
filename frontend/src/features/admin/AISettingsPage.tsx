import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Plug, ShieldCheck, Sparkles } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { Field } from "@/components/Field";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LinesSkeleton } from "@/components/Skeletons";
import { aiAdminApi, type AIConnectionTest } from "@/lib/api/endpoints";
import { notifyError, notifySuccess } from "@/lib/toast";
import { formatDateTime } from "@/lib/format";

const PROVIDER_LABEL: Record<string, string> = {
  gemini: "Google Gemini",
  openai: "OpenAI",
  groq: "Groq",
};

/** Where the key that will actually be used comes from — the thing an admin is
 *  really asking when they open this page. */
const SOURCE_COPY: Record<string, { label: string; tone: "success" | "info" | "warning" }> = {
  tenant: { label: "Your organisation's key", tone: "success" },
  environment: { label: "Platform default key", tone: "info" },
  unconfigured: { label: "No key configured", tone: "warning" },
};

/**
 * Admin Hub → AI. Set or rotate this organisation's model-provider key, choose a
 * provider, switch AI off entirely, and test the connection.
 *
 * The key is write-only by design: the server has no endpoint that returns it, so
 * this page shows only a masked hint. Rotating means typing a new one.
 */
export function AISettingsPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["ai", "admin", "config"], queryFn: aiAdminApi.config });
  const [apiKey, setApiKey] = React.useState("");
  const [testResult, setTestResult] = React.useState<AIConnectionTest | null>(null);

  const save = useMutation({
    mutationFn: aiAdminApi.update,
    onSuccess: (data) => {
      setApiKey("");
      qc.setQueryData(["ai", "admin", "config"], data);
      notifySuccess("AI settings saved");
    },
    onError: (e: unknown) => notifyError(e),
  });

  const test = useMutation({
    mutationFn: aiAdminApi.testConnection,
    onSuccess: (r) => {
      setTestResult(r);
      // The result is the message — a toast on top would just repeat it.
      if (r.ok) notifySuccess("Connection OK", r.detail);
    },
    onError: (e: unknown) => notifyError(e),
  });

  if (q.isLoading) return <LinesSkeleton lines={8} />;
  if (q.isError || !q.data) {
    return <p className="text-sm text-danger">Couldn't load the AI settings.</p>;
  }
  const cfg = q.data;
  const source = SOURCE_COPY[cfg.key_source] ?? SOURCE_COPY.unconfigured;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Administration"
        title="AI"
        description="Which model provider this organisation uses, and whether AI is on at all."
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* ── the switch ── */}
        <Panel title="AI features" icon={Sparkles}>
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Turning this off stops every AI feature in this organisation and stops
              any employee data being sent to a model provider. Your plan is
              unaffected — you can turn it back on at any time.
            </p>
            <div className="flex items-center justify-between rounded-lg border border-border p-3">
              <div className="min-w-0">
                <p className="text-sm font-medium">
                  AI is {cfg.enabled ? "on" : "off"} for this organisation
                </p>
                <p className="text-xs text-muted-foreground">
                  {cfg.enabled
                    ? "Assistants, drafts and summaries are available to your people."
                    : "No prompts leave this organisation."}
                </p>
              </div>
              <Button
                variant={cfg.enabled ? "outline" : "default"}
                onClick={() => save.mutate({ enabled: !cfg.enabled })}
                loading={save.isPending}
              >
                {cfg.enabled ? "Turn off" : "Turn on"}
              </Button>
            </div>
          </div>
        </Panel>

        {/* ── where the key comes from ── */}
        <Panel title="Connection" icon={Plug}>
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={source.tone}>{source.label}</Badge>
              {cfg.provider && <Badge variant="secondary">{PROVIDER_LABEL[cfg.provider] ?? cfg.provider}</Badge>}
            </div>
            <p className="text-sm text-muted-foreground">
              {cfg.key_source === "tenant"
                ? "Requests use the key stored below, and the spend is billed to your own provider account."
                : cfg.key_source === "environment"
                  ? "Requests use the platform's shared key. Add your own below to use your provider account instead."
                  : "No provider key is available, so AI features will report that they are unavailable rather than guessing."}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="outline" onClick={() => test.mutate()} loading={test.isPending}>
                Test connection
              </Button>
              {testResult && !testResult.ok && (
                <span className="text-sm text-danger">{testResult.detail}</span>
              )}
              {testResult?.ok && (
                <span className="text-sm text-success">
                  {testResult.detail}
                  {testResult.model ? ` (${testResult.model})` : ""}
                </span>
              )}
            </div>
          </div>
        </Panel>

        {/* ── the key ── */}
        <Panel title="Provider key" icon={KeyRound} className="lg:col-span-2">
          <div className="space-y-3">
            {!cfg.encryption_available && (
              <div className="rounded-lg border border-warning/40 bg-warning-subtle p-3 text-sm">
                <p className="font-medium text-foreground">
                  Storing a key isn't possible on this deployment yet.
                </p>
                <p className="mt-1 text-muted-foreground">
                  <code className="font-mono text-xs">FIELD_ENCRYPTION_KEY</code> is
                  not set, so a key could only be stored unencrypted — which we
                  refuse to do. Ask whoever runs this deployment to set it, then
                  come back.
                </p>
              </div>
            )}

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field label="Provider">
                <Select
                  value={cfg.provider || "inherit"}
                  onValueChange={(v) => save.mutate({ provider: v === "inherit" ? "" : v })}
                >
                  <SelectTrigger aria-label="AI provider">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="inherit">Use the platform default</SelectItem>
                    {cfg.available_providers.map((p) => (
                      <SelectItem key={p} value={p}>
                        {PROVIDER_LABEL[p] ?? p}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>

              <Field
                label={cfg.tenant_key_set ? "Replace key" : "API key"}
                hint={
                  cfg.tenant_key_set
                    ? `A key ending ${cfg.key_hint} is stored${cfg.key_set_at ? `, set ${formatDateTime(cfg.key_set_at)}` : ""}.`
                    : "Stored encrypted. We can never show it back to you."
                }
              >
                <Input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={cfg.tenant_key_set ? "Enter a new key to rotate" : "Paste your provider key"}
                  autoComplete="off"
                  spellCheck={false}
                  disabled={!cfg.encryption_available}
                />
              </Field>
            </div>

            <div className="flex flex-wrap justify-end gap-2">
              {cfg.tenant_key_set && (
                <Button
                  variant="outline"
                  className="text-danger"
                  onClick={() => save.mutate({ clear_api_key: true })}
                  loading={save.isPending}
                >
                  Remove key
                </Button>
              )}
              <Button
                onClick={() => save.mutate({ api_key: apiKey })}
                disabled={!apiKey.trim() || !cfg.encryption_available}
                loading={save.isPending}
              >
                {cfg.tenant_key_set ? "Rotate key" : "Save key"}
              </Button>
            </div>

            <p className="flex items-start gap-2 text-xs text-muted-foreground">
              <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" />
              <span>
                Keys are encrypted before they are written and are never shown, logged
                or returned by the API. Setting, rotating and removing a key are
                recorded in the audit log — the action and who did it, never the key.
              </span>
            </p>
          </div>
        </Panel>
      </div>
    </div>
  );
}
