import { Link } from "react-router-dom";
import { ArrowRight, ClipboardCheck, GitBranch, ShieldCheck, Sparkles } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/StatusBadge";
import { HitlBanner } from "@/components/Hitl";
import { useAuth } from "@/lib/auth/AuthContext";
import { ROLE_LABEL, type Role } from "@/lib/enums";

/**
 * Phase 0 landing — a styled welcome that proves the design system end-to-end.
 * Phase 1 replaces this with the action-first, role-aware dashboard.
 */
export function DashboardPage() {
  const { me, atLeast } = useAuth();

  const quickLinks = [
    { to: "/approvals", label: "Approvals inbox", icon: ClipboardCheck, min: "MANAGER" as Role },
    { to: "/succession", label: "Succession", icon: GitBranch, min: "MANAGER" as Role },
    { to: "/audit", label: "Audit console", icon: ShieldCheck, min: "HRBP" as Role },
  ].filter((l) => atLeast(l.min));

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={me ? `Signed in as ${ROLE_LABEL[me.role as Role]}` : undefined}
        title={`Welcome${me?.display ? `, ${me.display.split(" ")[0]}` : ""}`}
        description="Your Talbotiq Admin Hub. The foundation, design system, auth and data layer are live — feature screens roll out across the build phases."
      />

      <HitlBanner
        source="AI"
        confidence={0.86}
        message="Every AI or automated output in this product is a draft until a human approves it. You'll see this safety gate on reviews, feedback summaries, succession plans and JDs."
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {quickLinks.map((link) => (
          <Card key={link.to} className="transition-shadow hover:shadow-sm">
            <CardContent className="flex items-center justify-between p-5">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <link.icon className="h-4 w-4" />
                </div>
                <span className="text-sm font-medium">{link.label}</span>
              </div>
              <Button asChild variant="ghost" size="icon-sm">
                <Link to={link.to} aria-label={`Open ${link.label}`}>
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-ai" />
            Design system
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="mb-2 text-2xs font-semibold uppercase tracking-wide text-muted-foreground">
              Status vocabulary
            </p>
            <div className="flex flex-wrap gap-2">
              {[
                "DRAFT",
                "PENDING_HUMAN_REVIEW",
                "AI_DRAFTING",
                "APPROVED",
                "REJECTED",
                "FINALIZED",
                "PUBLISHED",
                "ON_TRACK",
                "AT_RISK",
                "CRITICAL",
                "GREEN",
                "AMBER",
                "RED",
              ].map((s) => (
                <StatusBadge key={s} status={s} />
              ))}
            </div>
          </div>
          <div>
            <p className="mb-2 text-2xs font-semibold uppercase tracking-wide text-muted-foreground">
              Actions
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm">Primary</Button>
              <Button size="sm" variant="outline">Outline</Button>
              <Button size="sm" variant="secondary">Secondary</Button>
              <Button size="sm" variant="premium">
                <Sparkles className="h-4 w-4" /> Upgrade
              </Button>
              <Button size="sm" variant="ghost">Ghost</Button>
              <Button size="sm" variant="destructive">Destructive</Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
