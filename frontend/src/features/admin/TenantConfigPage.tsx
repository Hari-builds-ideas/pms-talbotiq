import * as React from "react";
import { RotateCcw, Save, Settings } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { LinesSkeleton } from "@/components/Skeletons";
import { ErrorState } from "@/components/ErrorState";
import { Field } from "@/components/Field";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useSaveTenantConfig, useTenantConfig } from "./useAdmin";
import { notifySuccess } from "@/lib/toast";
import { mapApiError } from "@/lib/errors";

export function TenantConfigPage() {
  const { data, isLoading, isError, error, refetch } = useTenantConfig();
  const save = useSaveTenantConfig();
  const [text, setText] = React.useState<string>("");
  const [parseError, setParseError] = React.useState<string | null>(null);
  const [saveError, setSaveError] = React.useState<string | null>(null);
  const [dirty, setDirty] = React.useState(false);

  React.useEffect(() => {
    if (data) {
      setText(JSON.stringify(data.settings, null, 2));
      setDirty(false);
    }
  }, [data]);

  function onChange(value: string) {
    setText(value);
    setDirty(true);
    setSaveError(null);
    try {
      JSON.parse(value);
      setParseError(null);
    } catch {
      setParseError("Invalid JSON — fix the syntax before saving.");
    }
  }

  function reset() {
    if (data) {
      setText(JSON.stringify(data.settings, null, 2));
      setDirty(false);
      setParseError(null);
      setSaveError(null);
    }
  }

  async function onSave() {
    setSaveError(null);
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(text);
    } catch {
      setParseError("Invalid JSON — fix the syntax before saving.");
      return;
    }
    try {
      // Send the version we loaded → a concurrent admin's save makes ours 409.
      await save.mutateAsync({ settings: parsed, version: data?.version });
      notifySuccess("Tenant settings saved");
      setDirty(false);
    } catch (err) {
      setSaveError(mapApiError(err).message);
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Settings" title="Tenant Config"
        description="Tenant-level settings as a free-form JSON object (locale, fiscal year, feature toggles…)."
      />

      {isLoading ? (
        <Panel title="Settings" icon={Settings}>
          <LinesSkeleton lines={6} />
        </Panel>
      ) : isError ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : (
        <Panel
          title="Settings"
          icon={Settings}
          aside={dirty ? <span className="text-2xs text-warning">Unsaved changes</span> : undefined}
        >
          <div className="space-y-4">
            {saveError && (
              <Alert variant="danger">
                <AlertDescription>{saveError}</AlertDescription>
              </Alert>
            )}
            <Field label="settings (JSON)" error={parseError ?? undefined}>
              <Textarea
                value={text}
                onChange={(e) => onChange(e.target.value)}
                spellCheck={false}
                className="min-h-72 font-mono text-xs"
                aria-invalid={Boolean(parseError)}
              />
            </Field>
            <div className="flex items-center justify-end gap-2">
              <Button variant="outline" onClick={reset} disabled={!dirty || save.isPending}>
                <RotateCcw className="h-4 w-4" />
                Reset
              </Button>
              <Button onClick={onSave} loading={save.isPending} disabled={Boolean(parseError) || !dirty}>
                <Save className="h-4 w-4" />
                Save settings
              </Button>
            </div>
          </div>
        </Panel>
      )}
    </div>
  );
}
