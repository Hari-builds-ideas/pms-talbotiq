import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate, useLocation, Navigate } from "react-router-dom";
import { Building2, KeyRound, Loader2, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { authApi } from "@/lib/api/endpoints";
import { useAuth } from "@/lib/auth/AuthContext";
import { mapApiError } from "@/lib/errors";
import type { TokenPair } from "@/lib/types";

const USING_MOCKS = import.meta.env.VITE_USE_MOCKS === "true";

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
  const { status, completeLogin } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = React.useState<string | null>(null);
  const [challenge, setChallenge] = React.useState<string | null>(null);
  const from = (location.state as { from?: string } | null)?.from ?? "/";

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
        setChallenge(res.challenge ?? "");
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
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-sidebar-accent">
            <Building2 className="h-5 w-5" />
          </div>
          <span className="text-lg font-semibold">Talbotiq PMS</span>
        </div>
        <div className="max-w-md space-y-4">
          <h1 className="text-3xl font-semibold leading-tight">
            Talent intelligence & performance management for modern teams.
          </h1>
          <p className="text-sidebar-foreground/70">
            Reviews, succession, approvals and analytics — with a human in the
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
          © Talbotiq · Multi-tenant · Enterprise-grade
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
              <Button variant="outline" className="w-full" type="button" disabled>
                <KeyRound className="h-4 w-4" />
                Sign in with SSO
              </Button>

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
      const tokens = await authApi.mfaChallenge({ challenge, code });
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
