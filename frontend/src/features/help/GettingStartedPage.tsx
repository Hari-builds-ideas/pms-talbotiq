/**
 * In-app getting-started (item 16) — what a new admin should do, in order.
 *
 * The order is the one that avoids the dead ends: people before cycles (a review
 * cycle over an empty directory does nothing), reporting lines before team screens
 * (every manager view is scoped by them, so without them a manager sees an empty
 * team and assumes the product is broken).
 */
import { Link } from "react-router-dom";
import {
  BadgeCheck, Bot, ClipboardCheck, LifeBuoy, Target, Users,
} from "lucide-react";

import { SUPPORT_EMAIL } from "@/features/legal/LegalPages";
import { useAuth } from "@/lib/auth/AuthContext";

interface Step {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  body: string;
  to?: string;
  cta?: string;
}

const ADMIN_STEPS: Step[] = [
  {
    icon: Users,
    title: "1. Add your people",
    body:
      "Invite them individually, or import a CSV of the whole organisation. The import " +
      "reports problems row by row and skips only the rows it cannot read, so one bad " +
      "line never costs you the batch.",
    to: "/admin/users",
    cta: "Go to Employees",
  },
  {
    icon: Users,
    title: "2. Set reporting lines",
    body:
      "Every manager view is scoped by who reports to whom. Until the lines are set, a " +
      "manager signs in to an empty team and reasonably concludes the product is broken.",
    to: "/admin/users",
    cta: "Assign managers",
  },
  {
    icon: Target,
    title: "3. Open a cycle and set goals",
    body:
      "A cycle is the period reviews and scores belong to. Goals and KPIs hang off it — " +
      "so create the cycle first, then goals, or there is nothing for them to attach to.",
    to: "/goals",
    cta: "Go to Goals & OKRs",
  },
  {
    icon: ClipboardCheck,
    title: "4. Try one review end to end",
    body:
      "Run a single review from draft to approval before rolling it out. It is the " +
      "fastest way to see the approval chain your organisation will actually use.",
    to: "/reviews",
    cta: "Go to Reviews",
  },
  {
    icon: Bot,
    title: "5. Understand the AI gate",
    body:
      "AI drafts reviews, feedback summaries and recognition — and nothing it produces " +
      "is saved until a human approves it. Ask the assistant \"what can you do?\" for a " +
      "summary scoped to your role.",
  },
  {
    icon: BadgeCheck,
    title: "6. Check your plan and AI spend",
    body:
      "Your plan decides which features and how many seats are available. AI usage and " +
      "an estimated cost are on the billing screen, alongside the per-tenant budget " +
      "that caps it.",
    to: "/admin/billing",
    cta: "Go to Billing",
  },
];

const EVERYONE_STEPS: Step[] = [
  {
    icon: Target,
    title: "Your goals",
    body: "See what you are measured on this cycle and how far along each KPI is.",
    to: "/goals",
    cta: "Go to Goals",
  },
  {
    icon: ClipboardCheck,
    title: "Your reviews",
    body: "Reviews you are part of, and anything currently waiting on you.",
    to: "/reviews",
    cta: "Go to Reviews",
  },
  {
    icon: Bot,
    title: "The assistant",
    body:
      "Ask about your goals, KPIs, cycle score or reviews. It only ever sees what you " +
      "are allowed to see, and it prepares changes for your approval rather than making " +
      "them itself.",
  },
];

function StepCard({ step }: { step: Step }) {
  return (
    <li className="rounded-xl border border-border bg-card p-5">
      <div className="mb-2 flex items-center gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <step.icon className="h-[18px] w-[18px]" />
        </span>
        <h3 className="text-sm font-semibold">{step.title}</h3>
      </div>
      <p className="text-sm leading-relaxed text-muted-foreground">{step.body}</p>
      {step.to && step.cta ? (
        <Link
          to={step.to}
          className="mt-3 inline-block text-sm font-medium text-primary hover:underline"
        >
          {step.cta} →
        </Link>
      ) : null}
    </li>
  );
}

export function GettingStartedPage() {
  const { me } = useAuth();
  const isAdmin = me?.role === "ADMIN" || me?.role === "HRBP";
  const steps = isAdmin ? ADMIN_STEPS : EVERYONE_STEPS;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Getting started</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {isAdmin
            ? "Setting up your workspace, in the order that avoids dead ends."
            : "What you can do here, and where to find it."}
        </p>
      </header>

      <ul className="grid gap-4 sm:grid-cols-2">
        {steps.map((s) => (
          <StepCard key={s.title} step={s} />
        ))}
      </ul>

      <div className="rounded-xl border border-border bg-card p-5">
        <div className="mb-2 flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <LifeBuoy className="h-[18px] w-[18px]" />
          </span>
          <h3 className="text-sm font-semibold">Still stuck?</h3>
        </div>
        <p className="text-sm text-muted-foreground">
          Email{" "}
          <a className="font-medium text-primary hover:underline" href={`mailto:${SUPPORT_EMAIL}`}>
            {SUPPORT_EMAIL}
          </a>
          . See also our{" "}
          <Link to="/privacy" className="text-primary hover:underline">Privacy Policy</Link> and{" "}
          <Link to="/terms" className="text-primary hover:underline">Terms</Link>.
        </p>
      </div>
    </div>
  );
}
