import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { KeyRound, LaptopMinimal, ShieldCheck, User as UserIcon } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { Field } from "@/components/Field";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { LinesSkeleton } from "@/components/Skeletons";
import { authApi } from "@/lib/api/endpoints";
import { tokenStore } from "@/lib/auth/tokenStore";
import { notifyError, notifySuccess } from "@/lib/toast";
import { formatDateTime } from "@/lib/format";
import type { Profile } from "@/lib/types";

/** My Settings (PHASE2 L1.1/L1.3) — self-service profile, preferences, and the
 *  account-security surface (password, 2FA, sessions, login history, activity).
 *  Everything is self-scoped server-side; this page adds no new authority. */
export function SettingsPage() {
  const qc = useQueryClient();
  const profileQ = useQuery({ queryKey: ["auth", "profile"], queryFn: authApi.profile });
  const [params] = useSearchParams();

  // Email-change confirmation lands here (?email_change_token=…).
  const emailToken = params.get("email_change_token");
  React.useEffect(() => {
    if (!emailToken) return;
    authApi
      .emailChangeConfirm(emailToken)
      .then((r) => {
        notifySuccess("Email updated", `Your account email is now ${r.email}.`);
        void qc.invalidateQueries({ queryKey: ["auth", "profile"] });
      })
      .catch(() => notifyError(new Error("This confirmation link is invalid or expired.")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [emailToken]);

  if (profileQ.isLoading) return <LinesSkeleton lines={8} />;
  if (profileQ.isError || !profileQ.data) return <p className="text-sm text-danger">Couldn't load your profile.</p>;
  const p = profileQ.data;

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Account" title="My settings" description="Your profile, preferences and account security." />
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <ProfileCard p={p} />
        <NotificationPrefsCard p={p} />
        <PasswordCard />
        <MfaCard p={p} />
        <SessionsCard />
        <HistoryCard />
      </div>
    </div>
  );
}

function ProfileCard({ p }: { p: Profile }) {
  const qc = useQueryClient();
  const [displayName, setDisplayName] = React.useState(p.display_name ?? "");
  const [phone, setPhone] = React.useState(p.phone);
  const [timezone, setTimezone] = React.useState(p.timezone);
  const [language, setLanguage] = React.useState(p.language);
  const fileRef = React.useRef<HTMLInputElement>(null);

  const save = useMutation({
    mutationFn: () =>
      authApi.profileUpdate({ display_name: displayName, phone, timezone, language }),
    onSuccess: () => {
      notifySuccess("Profile saved");
      void qc.invalidateQueries({ queryKey: ["auth", "profile"] });
    },
    onError: (e: unknown) => notifyError(e),
  });
  const upload = useMutation({
    mutationFn: (file: File) => authApi.photoUpload(file),
    onSuccess: () => {
      notifySuccess("Photo updated");
      void qc.invalidateQueries({ queryKey: ["auth", "profile"] });
    },
    onError: (e: unknown) => notifyError(e),
  });

  return (
    <Panel title="Profile" icon={UserIcon}>
      <div className="space-y-3">
        <div className="flex items-center gap-3">
          {/* Avatar preview via the authenticated photo endpoint. */}
          {p.has_photo ? (
            <img src={`/api/auth/users/${p.id}/photo`} alt="Your avatar" className="h-14 w-14 rounded-full object-cover" />
          ) : (
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-secondary text-lg font-semibold">
              {(p.display || p.email)[0]?.toUpperCase()}
            </div>
          )}
          <div className="space-x-2">
            <input
              ref={fileRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) upload.mutate(f);
              }}
            />
            <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()} loading={upload.isPending}>
              Upload photo
            </Button>
            <span className="text-2xs text-muted-foreground">JPEG/PNG/WebP · max 2 MB</span>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Full name"><Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} /></Field>
          <Field label="Phone"><Input value={phone} onChange={(e) => setPhone(e.target.value)} /></Field>
          <Field label="Time zone" hint='e.g. "Asia/Kuala_Lumpur"'>
            <Input value={timezone} onChange={(e) => setTimezone(e.target.value)} />
          </Field>
          <Field label="Language"><Input value={language} onChange={(e) => setLanguage(e.target.value)} /></Field>
        </div>
        {/* Org-controlled facts — read-only here (your admin maintains them). */}
        <div className="flex flex-wrap gap-x-4 gap-y-1 rounded-md bg-secondary/40 px-3 py-2 text-xs text-muted-foreground">
          <span>Email <span className="font-medium text-foreground">{p.email}</span></span>
          <span>Role <span className="font-medium text-foreground">{p.role}</span></span>
          {p.title && <span>Title <span className="font-medium text-foreground">{p.title}</span></span>}
          {p.department && <span>Dept <span className="font-medium text-foreground">{p.department}</span></span>}
          {p.employee_id && <span>ID <span className="font-medium text-foreground">{p.employee_id}</span></span>}
        </div>
        <EmailChangeRow />
        <div className="flex justify-end">
          <Button onClick={() => save.mutate()} loading={save.isPending}>Save profile</Button>
        </div>
      </div>
    </Panel>
  );
}

function EmailChangeRow() {
  const [open, setOpen] = React.useState(false);
  const [newEmail, setNewEmail] = React.useState("");
  const [pw, setPw] = React.useState("");
  const m = useMutation({
    mutationFn: () => authApi.emailChangeRequest({ new_email: newEmail, current_password: pw }),
    onSuccess: () => {
      notifySuccess("Check your new inbox", "We sent a confirmation link to the new address.");
      setOpen(false); setNewEmail(""); setPw("");
    },
    onError: (e: unknown) => notifyError(e),
  });
  if (!open) {
    return (
      <button type="button" className="text-xs font-medium text-primary hover:underline" onClick={() => setOpen(true)}>
        Change email…
      </button>
    );
  }
  return (
    <div className="space-y-2 rounded-md border border-border p-3">
      <Field label="New email"><Input type="email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} /></Field>
      <Field label="Current password"><Input type="password" value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={() => setOpen(false)}>Cancel</Button>
        <Button size="sm" onClick={() => m.mutate()} loading={m.isPending} disabled={!newEmail || !pw}>
          Send confirmation
        </Button>
      </div>
    </div>
  );
}

const NOTIFY_KEYS: Array<{ key: string; label: string }> = [
  { key: "email", label: "Email" },
  { key: "slack", label: "Slack" },
  { key: "in_app", label: "In-app" },
];

function NotificationPrefsCard({ p }: { p: Profile }) {
  const qc = useQueryClient();
  const stored = (p.preferences?.notifications as Record<string, boolean> | undefined) ?? {};
  const [prefs, setPrefs] = React.useState<Record<string, boolean>>({
    email: stored.email ?? true, slack: stored.slack ?? true, in_app: stored.in_app ?? true,
  });
  const save = useMutation({
    mutationFn: () => authApi.profileUpdate({ preferences: { ...p.preferences, notifications: prefs } }),
    onSuccess: () => {
      notifySuccess("Preferences saved");
      void qc.invalidateQueries({ queryKey: ["auth", "profile"] });
    },
    onError: (e: unknown) => notifyError(e),
  });
  return (
    <Panel title="Notification preferences" icon={ShieldCheck}>
      <div className="space-y-2">
        {NOTIFY_KEYS.map(({ key, label }) => (
          <label key={key} className="flex items-center justify-between text-sm">
            <span>{label}</span>
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-input"
              checked={prefs[key]}
              onChange={(e) => setPrefs((s) => ({ ...s, [key]: e.target.checked }))}
            />
          </label>
        ))}
        <p className="text-2xs text-muted-foreground">
          Preferences are stored per channel. Delivery today: password-reset email is live; other
          email/Slack notifications roll out with the notification center (v2).
        </p>
        <div className="flex justify-end">
          <Button size="sm" onClick={() => save.mutate()} loading={save.isPending}>Save preferences</Button>
        </div>
      </div>
    </Panel>
  );
}

function PasswordCard() {
  const [current, setCurrent] = React.useState("");
  const [next, setNext] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const m = useMutation({
    mutationFn: () => authApi.passwordChange({ current_password: current, new_password: next }),
    onSuccess: (r) => {
      // Every OTHER session was revoked server-side; adopt the fresh pair for this one.
      if (r.access && r.refresh) tokenStore.set(r.access, r.refresh);
      notifySuccess("Password changed", "All other sessions were signed out.");
      setCurrent(""); setNext(""); setConfirm("");
    },
    onError: (e: unknown) => notifyError(e),
  });
  return (
    <Panel title="Change password" icon={KeyRound}>
      <div className="space-y-3">
        <Field label="Current password"><Input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} /></Field>
        <Field label="New password"><Input type="password" value={next} onChange={(e) => setNext(e.target.value)} /></Field>
        <Field label="Confirm new password" error={confirm && confirm !== next ? "Passwords don't match." : undefined}>
          <Input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        </Field>
        <div className="flex justify-end">
          <Button onClick={() => m.mutate()} loading={m.isPending} disabled={!current || !next || next !== confirm}>
            Change password
          </Button>
        </div>
      </div>
    </Panel>
  );
}

function MfaCard({ p }: { p: Profile }) {
  const qc = useQueryClient();
  const [enroll, setEnroll] = React.useState<{ secret: string; config_url: string } | null>(null);
  const [code, setCode] = React.useState("");
  const [pw, setPw] = React.useState("");
  const refresh = () => void qc.invalidateQueries({ queryKey: ["auth", "profile"] });

  const start = useMutation({
    mutationFn: () => authApi.mfaEnroll(),
    onSuccess: setEnroll,
    onError: (e: unknown) => notifyError(e),
  });
  const confirm = useMutation({
    mutationFn: () => authApi.mfaEnrollConfirm({ code }),
    onSuccess: () => { notifySuccess("Two-factor enabled"); setEnroll(null); setCode(""); refresh(); },
    onError: (e: unknown) => notifyError(e),
  });
  const disable = useMutation({
    mutationFn: () => authApi.mfaDisable(pw),
    onSuccess: () => { notifySuccess("Two-factor disabled"); setPw(""); refresh(); },
    onError: (e: unknown) => notifyError(e),
  });

  return (
    <Panel title="Two-factor authentication" icon={ShieldCheck}
      aside={<Badge variant={p.mfa_enabled ? "success" : "muted"}>{p.mfa_enabled ? "Enabled" : "Off"}</Badge>}>
      {p.mfa_enabled ? (
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">TOTP is active on your account.</p>
          <Field label="Current password (to disable)">
            <Input type="password" value={pw} onChange={(e) => setPw(e.target.value)} />
          </Field>
          <div className="flex justify-end">
            <Button variant="outline" size="sm" onClick={() => disable.mutate()} loading={disable.isPending} disabled={!pw}>
              Disable 2FA
            </Button>
          </div>
        </div>
      ) : enroll ? (
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">
            Add this secret to your authenticator app, then confirm with a code:
          </p>
          <p className="break-all rounded-md bg-secondary/50 px-3 py-2 font-mono text-xs">{enroll.secret}</p>
          <p className="break-all text-2xs text-muted-foreground">{enroll.config_url}</p>
          <Field label="6-digit code"><Input inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value)} /></Field>
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setEnroll(null)}>Cancel</Button>
            <Button size="sm" onClick={() => confirm.mutate()} loading={confirm.isPending} disabled={code.length !== 6}>
              Confirm & enable
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">Protect your account with an authenticator app.</p>
          <Button size="sm" onClick={() => start.mutate()} loading={start.isPending}>Enable 2FA</Button>
        </div>
      )}
    </Panel>
  );
}

function SessionsCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["auth", "sessions"], queryFn: authApi.sessions });
  const refresh = () => void qc.invalidateQueries({ queryKey: ["auth", "sessions"] });
  const revoke = useMutation({
    mutationFn: (id: string) => authApi.sessionRevoke(id),
    onSuccess: () => { notifySuccess("Session revoked"); refresh(); },
    onError: (e: unknown) => notifyError(e),
  });
  const revokeOthers = useMutation({
    mutationFn: authApi.sessionsRevokeOthers,
    onSuccess: (r) => { notifySuccess(`Signed out ${r.revoked} other session(s)`); refresh(); },
    onError: (e: unknown) => notifyError(e),
  });
  return (
    <Panel title="Active sessions" icon={LaptopMinimal}
      aside={<Button variant="outline" size="sm" onClick={() => revokeOthers.mutate()} loading={revokeOthers.isPending}>Sign out others</Button>}>
      {q.isLoading ? (
        <LinesSkeleton lines={3} />
      ) : (
        <ul className="divide-y divide-border">
          {(q.data ?? []).map((s) => (
            <li key={s.id} className="flex items-center justify-between gap-3 py-2 text-sm">
              <div className="min-w-0">
                <p className="truncate font-medium">
                  {s.user_agent || "Unknown device"} {s.current && <Badge variant="success" className="ml-1">This device</Badge>}
                </p>
                <p className="text-2xs text-muted-foreground">{s.ip ?? "—"} · last seen {formatDateTime(s.last_seen)}</p>
              </div>
              {!s.current && (
                <Button variant="ghost" size="sm" className="text-danger" onClick={() => revoke.mutate(s.id)}>
                  Revoke
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function HistoryCard() {
  const historyQ = useQuery({ queryKey: ["auth", "login-history"], queryFn: authApi.loginHistory });
  const activityQ = useQuery({ queryKey: ["auth", "my-activity"], queryFn: authApi.myActivity });
  return (
    <Panel title="Login history & activity" icon={ShieldCheck}>
      {historyQ.isLoading || activityQ.isLoading ? (
        <LinesSkeleton lines={4} />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <p className="mb-1 text-2xs font-semibold uppercase tracking-wide text-muted-foreground">Sign-ins</p>
            <ul className="space-y-1 text-xs">
              {(historyQ.data ?? []).slice(0, 8).map((e, i) => (
                <li key={i} className="flex justify-between gap-2">
                  <span className={e.event.includes("FAILED") || e.event === "LOCKOUT" ? "text-danger" : ""}>{e.event}</span>
                  <span className="text-muted-foreground">{formatDateTime(e.created_at)}</span>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="mb-1 text-2xs font-semibold uppercase tracking-wide text-muted-foreground">Recent activity</p>
            <ul className="space-y-1 text-xs">
              {(activityQ.data ?? []).slice(0, 8).map((a, i) => (
                <li key={i} className="flex justify-between gap-2">
                  <span className="truncate">{a.action}</span>
                  <span className="shrink-0 text-muted-foreground">{formatDateTime(a.created_at)}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </Panel>
  );
}
