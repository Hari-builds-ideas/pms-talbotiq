import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useNavigate, Navigate } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { authApi } from "@/lib/api/endpoints";
import { useAuth } from "@/lib/auth/AuthContext";
import { mapApiError } from "@/lib/errors";
import { BRAND, BrandWordmark } from "@/brand";
import type { TokenPair } from "@/lib/types";

const signupSchema = z.object({
  org_name: z.string().min(2, "Enter your organization name"),
  display_name: z.string().min(2, "Enter your name"),
  email: z.string().min(1, "Email is required").email("Enter a valid email"),
  password: z.string().min(8, "Use at least 8 characters"),
});
type SignupValues = z.infer<typeof signupSchema>;

/** Self-serve workspace creation (PROD_B). A brand-new organization creates its
 *  workspace, becomes the first admin, and is logged straight in. */
export function SignupPage() {
  const { status, completeLogin } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = React.useState<string | null>(null);
  const [workspace, setWorkspace] = React.useState<string | null>(null);

  const form = useForm<SignupValues>({
    resolver: zodResolver(signupSchema),
    defaultValues: { org_name: "", display_name: "", email: "", password: "" },
  });

  if (status === "authenticated") return <Navigate to="/" replace />;

  async function onSubmit(values: SignupValues) {
    setError(null);
    try {
      const res = await authApi.signup(values);
      setWorkspace(res.tenant_slug);
      await completeLogin(res as TokenPair);
      navigate("/", { replace: true });
    } catch (err) {
      const mapped = mapApiError(err);
      setError(mapped.message);
    }
  }

  return (
    <div className="flex min-h-screen min-h-[100dvh] pt-safe pb-safe">
      {/* Brand panel */}
      <div className="relative hidden w-1/2 flex-col justify-between bg-sidebar p-12 text-white lg:flex">
        <div className="flex items-center gap-2.5">
          <BrandWordmark onDark className="h-12 w-auto" />
        </div>
        <div className="max-w-md space-y-4">
          <h1 className="text-3xl font-semibold leading-tight">
            Start your team's performance workspace in a minute.
          </h1>
          <p className="text-sidebar-foreground/70">
            Create your organization, invite or import your people, and run
            goals, reviews and feedback — with a human in the loop on every AI
            decision.
          </p>
          <ul className="space-y-2 text-sm text-sidebar-foreground/80">
            {["Your own isolated workspace", "You become the admin", "Free to start"].map(
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
          <div className="mb-6 space-y-1">
            <h2 className="text-2xl font-semibold tracking-tight">Create your workspace</h2>
            <p className="text-sm text-muted-foreground">
              Set up {BRAND.name} for your organization.
            </p>
          </div>

          {error && (
            <Alert variant="danger" className="mb-4">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
            <Field label="Organization name" error={form.formState.errors.org_name?.message}>
              <Input placeholder="Acme Inc." autoComplete="organization" {...form.register("org_name")} />
            </Field>
            <Field label="Your name" error={form.formState.errors.display_name?.message}>
              <Input placeholder="Jordan Lee" autoComplete="name" {...form.register("display_name")} />
            </Field>
            <Field label="Work email" error={form.formState.errors.email?.message}>
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
                autoComplete="new-password"
                placeholder="Create a strong password"
                {...form.register("password")}
              />
            </Field>

            <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
              Create workspace
            </Button>
          </form>

          {workspace && (
            <p className="mt-3 text-center text-2xs text-muted-foreground">
              Workspace ID: <span className="font-semibold">{workspace}</span> — use it to sign in.
            </p>
          )}

          <p className="mt-6 text-center text-sm text-muted-foreground">
            Already have a workspace?{" "}
            <Link to="/login" className="font-medium text-primary hover:underline">
              Sign in
            </Link>
          </p>
        </div>
      </div>
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
