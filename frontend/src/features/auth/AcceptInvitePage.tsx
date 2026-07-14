import * as React from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/Field";
import { LinesSkeleton } from "@/components/Skeletons";
import { BRAND, BrandMark } from "@/brand";
import { api } from "@/lib/api/client";
import { mapApiError } from "@/lib/errors";

interface InviteDetail {
  email: string;
  tenant_name: string;
  role: string;
}

/** Public invite-acceptance (PHASE2 L1.2): the emailed link lands here; the
 *  invitee sets a name + password and joins the invite's tenant with its role. */
export function AcceptInvitePage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token") ?? "";
  const [name, setName] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  const detailQ = useQuery<InviteDetail>({
    queryKey: ["invite", token],
    queryFn: async () => (await api.get(`/auth/invitations/${token}`)).data,
    enabled: Boolean(token),
    retry: false,
  });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("Passwords don't match.");
      return;
    }
    setBusy(true);
    try {
      await api.post(`/auth/invitations/${token}/accept`, {
        display_name: name,
        password,
      });
      navigate("/login", { replace: true });
    } catch (err) {
      setError(mapApiError(err).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-6">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <BrandMark onDark className="h-6 w-6" />
          </div>
          <span className="text-lg font-semibold">{BRAND.name}</span>
        </div>
        {!token || detailQ.isError ? (
          <p className="rounded-lg border border-border bg-secondary/40 p-4 text-sm text-muted-foreground">
            This invitation is invalid, expired, or was revoked. Ask your admin to send a new one.
          </p>
        ) : detailQ.isLoading || !detailQ.data ? (
          <LinesSkeleton lines={4} />
        ) : (
          <>
            <div>
              <h1 className="text-xl font-semibold">Join {detailQ.data.tenant_name}</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                You're joining as <span className="font-medium">{detailQ.data.role}</span> with{" "}
                <span className="font-medium">{detailQ.data.email}</span>.
              </p>
            </div>
            <form onSubmit={submit} className="space-y-4">
              {error && <p className="rounded-md bg-danger-subtle px-3 py-2 text-sm text-danger">{error}</p>}
              <Field label="Your name">
                <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
              </Field>
              <Field label="Password" required>
                <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
              </Field>
              <Field label="Confirm password" required>
                <Input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
              </Field>
              <Button type="submit" className="w-full" loading={busy} disabled={!password || !confirm}>
                <UserPlus className="h-4 w-4" /> Create my account
              </Button>
            </form>
          </>
        )}
        <p className="text-sm text-muted-foreground">
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-primary hover:underline">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
