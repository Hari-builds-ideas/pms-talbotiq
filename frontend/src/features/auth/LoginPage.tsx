import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useNavigate, useLocation, Navigate } from "react-router-dom";
import { KeyRound, Loader2, ShieldCheck } from "lucide-react";
import { BRAND, BrandWordmark } from "@/brand";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { authApi } from "@/lib/api/endpoints";
import { useAuth } from "@/lib/auth/AuthContext";
import { landingPathFor } from "@/app/nav";
import { mapApiError } from "@/lib/errors";
import type { TokenPair } from "@/lib/types";

const USING_MOCKS = import.meta.env.VITE_USE_MOCKS === "true";
// Sign-in-with-Google is shown only when the deploy has been configured for it
// (the human's real Google OAuth creds on the backend + this build flag). Off by
// default so an unconfigured deploy never shows a button that errors.
const GOOGLE_SSO = import.meta.env.VITE_GOOGLE_SSO_ENABLED === "true";

const loginSchema = z.object({
  tenant: z.string().min(1, "Workspace is required"),
  email: z.string().min(1, "Email is required").email("Enter a valid email"),
  password: z.string().min(1, "Password is required"),
});
type LoginValues = z.infer<typeof loginSchema>;

const DEMO_ACCOUNTS = [
  { label: "Admin", email: "admin@acme.test" },
  { label: "HRBP", email: "hrbp@acme.test" },
  { label: "Manager (MFA)", email: "ada@acme.test" },
];

export function LoginPage() {
  const { status, completeLogin, me } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = React.useState<string | null>(null);
  const [challenge, setChallenge] = React.useState<string | null>(null);
  const rawFrom = (location.state as { from?: string } | null)?.from ?? "/";
  // Clamp a role-forbidden target back to the dashboard so we never land on a 403 page.
  const from = landingPathFor(rawFrom, me?.role);

  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { tenant: "acme", email: "", password: "" },
  });

  if (status === "authenticated") return <Navigate to={from} replace />;

  async function onSubmit(values: LoginValues) {
    setError(null);
    try {
      const res = await authApi.login({
        email: values.email,
        password: values.password,
        tenant_slug: values.tenant,
      });
      if (res.mfa_required) {
        setChallenge(res.mfa_token ?? "");
        return;
      }
      if (res.access && res.refresh) {
        await completeLogin(res as TokenPair);
        navigate(from, { replace: true });
      }
    } catch (err) {
      const mapped = mapApiError(err);
      setError(
        mapped.status === 401
          ? "Those credentials didn't work. Check your email and password."
          : mapped.message,
      );
    }
  }

  return (
    <div className="flex min-h-screen">
      {/* Brand panel */}
      <div className="relative hidden w-1/2 flex-col justify-between bg-sidebar p-12 text-white lg:flex">
        <div className="flex items-center gap-2.5">
          <BrandWordmark onDark className="h-12 w-auto" />
        </div>
        <div className="max-w-md space-y-4">
          <h1 className="text-3xl font-semibold leading-tight">
            {BRAND.tagline}
          </h1>
          <p className="text-sidebar-foreground/70">
            Goals, reviews, feedback and approvals — with a human in the
            loop on every AI decision.
          </p>
          <ul className="space-y-2 text-sm text-sidebar-foreground/80">
            {["Human-gated AI drafts", "Role-based access control", "Audited by design"].map(
              (f) => (
                <li key={f} className="flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4 text-sidebar-accent" />
                  {f}
                </li>
              ),
            )}
          </ul>
        </div>
        <p className="text-2xs text-sidebar-muted">
          © {BRAND.name} · Multi-tenant · Enterprise-grade
        </p>
      </div>

      {/* Form panel */}
      <div className="flex w-full flex-col items-center justify-center px-6 lg:w-1/2">
        <div className="w-full max-w-sm">
          {challenge === null ? (
            <>
              <div className="mb-6 space-y-1">
                <h2 className="text-2xl font-semibold tracking-tight">Sign in</h2>
                <p className="text-sm text-muted-foreground">
                  Enter your workspace credentials to continue.
                </p>
              </div>

              {error && (
                <Alert variant="danger" className="mb-4">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
                <Field label="Workspace" error={form.formState.errors.tenant?.message}>
                  <Input placeholder="acme" {...form.register("tenant")} />
                </Field>
                <Field label="Email" error={form.formState.errors.email?.message}>
                  <Input
                    type="email"
                    autoComplete="username"
                    placeholder="you@company.com"
                    {...form.register("email")}
                  />
                </Field>
                <Field label="Password" error={form.formState.errors.password?.message}>
                  <Input
                    type="password"
                    autoComplete="current-password"
                    placeholder="••••••••"
                    {...form.register("password")}
                  />
                </Field>
                <p className="text-right text-xs">
                  <Link to="/forgot-password" className="font-medium text-primary hover:underline">
                    Forgot password?
                  </Link>
                </p>

                <Button
                  type="submit"
                  className="w-full"
                  loading={form.formState.isSubmitting}
                >
                  Sign in
                </Button>
              </form>

              <div className="my-5 flex items-center gap-3 text-2xs text-muted-foreground">
                <span className="h-px flex-1 bg-border" />
                OR
                <span className="h-px flex-1 bg-border" />
              </div>
              {GOOGLE_SSO ? (
                <Button
                  variant="outline"
                  className="w-full"
                  type="button"
                  onClick={() => {
                    // Full-page redirect into allauth's OIDC flow; the workspace
                    // slug tells the tenant-binding adapter which tenant to bind
                    // (no JIT — the Google identity must already be a user there).
                    const slug = encodeURIComponent(form.getValues("tenant") || "");
                    window.location.href = `/accounts/oidc/google/login/?process=login&tenant=${slug}`;
                  }}
                >
                  <KeyRound className="h-4 w-4" />
                  Sign in with Google
                </Button>
              ) : (
                <Button variant="outline" className="w-full" type="button" disabled>
                  <KeyRound className="h-4 w-4" />
                  Sign in with SSO
                </Button>
              )}

              <p className="mt-6 text-center text-sm text-muted-foreground">
                New organization?{" "}
                <Link to="/signup" className="font-medium text-primary hover:underline">
                  Create your workspace
                </Link>
              </p>

              {USING_MOCKS && (
                <div className="mt-6 rounded-lg border border-dashed border-border bg-secondary/40 p-3">
                  <p className="mb-2 text-2xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Demo accounts · any password works
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {DEMO_ACCOUNTS.map((a) => (
                      <button
                        key={a.email}
                        type="button"
                        className="rounded-full border border-border bg-card px-2.5 py-1 text-xs hover:bg-secondary"
                        onClick={() => {
                          form.setValue("email", a.email);
                          form.setValue("password", "demo1234");
                        }}
                      >
                        {a.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <MfaStep
              challenge={challenge}
              onCancel={() => setChallenge(null)}
              onVerified={async (tokens) => {
                await completeLogin(tokens);
                navigate(from, { replace: true });
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function MfaStep({
  challenge,
  onVerified,
  onCancel,
}: {
  challenge: string;
  onVerified: (tokens: TokenPair) => Promise<void>;
  onCancel: () => void;
}) {
  const [code, setCode] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);

  async function verify(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!/^\d{6}$/.test(code)) {
      setError("Enter the 6-digit code from your authenticator.");
      return;
    }
    setLoading(true);
    try {
      const tokens = await authApi.mfaChallenge({ mfa_token: challenge, code });
      await onVerified(tokens);
    } catch {
      setError("That code wasn't valid. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div className="mb-6 space-y-1">
        <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <ShieldCheck className="h-5 w-5" />
        </div>
        <h2 className="text-2xl font-semibold tracking-tight">Two-factor</h2>
        <p className="text-sm text-muted-foreground">
          Enter the 6-digit code from your authenticator app.
        </p>
      </div>
      {error && (
        <Alert variant="danger" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <form onSubmit={verify} className="space-y-4">
        <Field label="Authentication code">
          <Input
            inputMode="numeric"
            autoFocus
            maxLength={6}
            placeholder="123456"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            className="text-center text-lg tracking-[0.4em]"
          />
        </Field>
        <Button type="submit" className="w-full" disabled={loading}>
          {loading && <Loader2 className="h-4 w-4 animate-spin" />}
          Verify
        </Button>
        <Button type="button" variant="ghost" className="w-full" onClick={onCancel}>
          Back
        </Button>
      </form>
      {USING_MOCKS && (
        <p className="mt-4 text-center text-2xs text-muted-foreground">
          Demo: any 6 digits (e.g. 123456) will verify.
        </p>
      )}
    </div>
  );
}

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
      {error && <p className="text-xs text-danger">{error}</p>}
    </div>
  );
}
