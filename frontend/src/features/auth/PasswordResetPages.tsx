import * as React from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { KeyRound, MailCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/Field";
import { BRAND, BrandMark } from "@/brand";
import { authApi } from "@/lib/api/endpoints";
import { mapApiError } from "@/lib/errors";

/** Shared centered card shell for the public reset pages (matches LoginPage tone). */
function AuthShell({ title, subtitle, children }: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen min-h-[100dvh] flex-col items-center justify-center bg-background px-6 pt-safe pb-safe">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <BrandMark onDark className="h-6 w-6" />
          </div>
          <span className="text-lg font-semibold">{BRAND.name}</span>
        </div>
        <div>
          <h1 className="text-xl font-semibold">{title}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
        </div>
        {children}
        <p className="text-sm text-muted-foreground">
          <Link to="/login" className="font-medium text-primary hover:underline">
            Back to sign in
          </Link>
        </p>
      </div>
    </div>
  );
}

/** Step 1 — request the reset email. Always shows the same confirmation
 *  (the server never reveals whether an account exists). */
export function ForgotPasswordPage() {
  const [tenant, setTenant] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [sent, setSent] = React.useState(false);
  const [busy, setBusy] = React.useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await authApi.passwordResetRequest({ tenant_slug: tenant.trim(), email: email.trim() });
    } catch {
      /* same message either way — no enumeration */
    } finally {
      setSent(true);
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title="Forgot your password?"
      subtitle="Enter your workspace and email — if an account exists, we'll email a reset link."
    >
      {sent ? (
        <div className="flex items-start gap-3 rounded-lg border border-border bg-secondary/40 p-4 text-sm">
          <MailCheck className="mt-0.5 h-4 w-4 shrink-0 text-success" />
          <p>
            If an account exists for <span className="font-medium">{email}</span>, a reset link is on
            its way. The link is single-use and expires — check spam if it doesn't arrive.
          </p>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <Field label="Workspace" required>
            <Input value={tenant} onChange={(e) => setTenant(e.target.value)} placeholder="acme" autoFocus />
          </Field>
          <Field label="Email" required>
            <Input type="email" inputMode="email" autoComplete="email" autoCapitalize="none" autoCorrect="off" spellCheck={false} value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
          </Field>
          <Button type="submit" className="w-full" loading={busy} disabled={!tenant.trim() || !email.trim()}>
            Send reset link
          </Button>
        </form>
      )}
    </AuthShell>
  );
}

/** Step 2 — the emailed link lands here with ?tenant&uid&token; set a new password. */
export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const tenant = params.get("tenant") ?? "";
  const uid = params.get("uid") ?? "";
  const token = params.get("token") ?? "";
  const [password, setPassword] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  const linkValid = Boolean(tenant && uid && token);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("Passwords don't match.");
      return;
    }
    setBusy(true);
    try {
      await authApi.passwordResetConfirm({ tenant_slug: tenant, uid, token, new_password: password });
      navigate("/login", { replace: true });
    } catch (err) {
      const mapped = mapApiError(err);
      setError(
        mapped.status === 400
          ? "This reset link is invalid or has expired — request a new one."
          : mapped.message,
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell title="Set a new password" subtitle="Choose a strong password for your account.">
      {!linkValid ? (
        <p className="rounded-lg border border-border bg-secondary/40 p-4 text-sm text-muted-foreground">
          This reset link is incomplete.{" "}
          <Link to="/forgot-password" className="font-medium text-primary hover:underline">
            Request a new one
          </Link>
          .
        </p>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          {error && <p className="rounded-md bg-danger-subtle px-3 py-2 text-sm text-danger">{error}</p>}
          <Field label="New password" required>
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus />
          </Field>
          <Field label="Confirm new password" required>
            <Input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          </Field>
          <Button type="submit" className="w-full" loading={busy} disabled={!password || !confirm}>
            <KeyRound className="h-4 w-4" /> Reset password
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
