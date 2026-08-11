/**
 * Privacy Policy, Terms of Service and Support — public, unauthenticated routes.
 *
 * ⚠️ THE BODY TEXT IS A DRAFT AND IS NOT LEGAL ADVICE.
 *
 * These exist because a product that processes employee performance data cannot be
 * sold without them, and because the routes, links and footer need to exist before
 * the words do. Every draft section carries a visible review banner: a page that
 * *looks* like a reviewed policy but was written by an engineer is worse than an
 * obviously-unfinished one, because a customer's legal team will skim it and assume
 * somebody signed it off.
 *
 * Replace the bodies with counsel-approved text, then delete `DRAFT_BANNER` — the
 * test asserts the banner is present, so removing it deliberately is a decision
 * somebody has to make in the diff.
 */
import { Link } from "react-router-dom";

import { BRAND } from "@/brand";

/** Support address. Set VITE_SUPPORT_EMAIL at build time; the fallback is
 *  deliberately obvious rather than a plausible-looking address nobody reads. */
export const SUPPORT_EMAIL =
  import.meta.env.VITE_SUPPORT_EMAIL || "support@example.com";

const UPDATED = "12 August 2026";

function DraftBanner() {
  return (
    <div
      role="note"
      className="mb-8 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900"
    >
      <strong className="font-semibold">Draft — pending legal review.</strong> This text
      is a working draft and is not a binding agreement. Contact{" "}
      <a className="underline" href={`mailto:${SUPPORT_EMAIL}`}>
        {SUPPORT_EMAIL}
      </a>{" "}
      with any question about how your data is handled.
    </div>
  );
}

function Shell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-6 py-5">
          <Link to="/login" className="text-base font-bold tracking-tight">
            {BRAND.shortName}
          </Link>
          <nav className="flex gap-4 text-sm text-muted-foreground">
            <Link to="/privacy" className="hover:text-foreground">Privacy</Link>
            <Link to="/terms" className="hover:text-foreground">Terms</Link>
            <Link to="/support" className="hover:text-foreground">Support</Link>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="mb-1 text-3xl font-semibold tracking-tight">{title}</h1>
        <p className="mb-8 text-sm text-muted-foreground">Last updated {UPDATED}</p>
        {children}
      </main>
    </div>
  );
}

function Section({ heading, children }: { heading: string; children: React.ReactNode }) {
  return (
    <section className="mb-7">
      <h2 className="mb-2 text-lg font-semibold">{heading}</h2>
      <div className="space-y-2 text-sm leading-relaxed text-muted-foreground">
        {children}
      </div>
    </section>
  );
}

export function PrivacyPage() {
  return (
    <Shell title="Privacy Policy">
      <DraftBanner />
      <Section heading="What we process">
        <p>
          {BRAND.name} is a performance management system operated on behalf of your
          employer. It processes work-related personal data: your name and work email,
          reporting line, goals and KPIs, review and feedback records, check-ins,
          recognition, and audit records of actions taken in the product.
        </p>
      </Section>
      <Section heading="Who controls it">
        <p>
          Your employer is the data controller and decides why the data is processed.
          {" "}{BRAND.name} acts as a processor, handling it on their instructions.
          Requests to access, correct or delete your data should go to your employer
          first; we support them in fulfilling those requests.
        </p>
      </Section>
      <Section heading="Tenant isolation">
        <p>
          Each customer's data sits in a separate logical tenant, and every request is
          scoped to the tenant of the signed-in user. Staff of one organisation cannot
          read another's records.
        </p>
      </Section>
      <Section heading="AI processing">
        <p>
          Some features send work data to a third-party language-model provider to draft
          text or summarise performance information. Every AI output is held for human
          review before it takes effect — nothing is written to a record on the model's
          say-so. AI features can be disabled for your organisation.
        </p>
      </Section>
      <Section heading="Retention and security">
        <p>
          Data is retained for as long as your employer's account is active, plus any
          period their own policy requires. Access is role-based, transport is encrypted,
          and privileged actions are written to an append-only audit log.
        </p>
      </Section>
      <Section heading="Contact">
        <p>
          Questions about this policy: <a className="underline" href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>.
        </p>
      </Section>
    </Shell>
  );
}

export function TermsPage() {
  return (
    <Shell title="Terms of Service">
      <DraftBanner />
      <Section heading="The agreement">
        <p>
          These terms govern use of {BRAND.name}. Where your employer has signed a
          separate written agreement, that agreement takes precedence over this page.
        </p>
      </Section>
      <Section heading="Accounts">
        <p>
          Accounts are issued by your organisation's administrator and are personal to
          you. Keep your credentials secret and tell your administrator promptly if you
          believe an account has been compromised.
        </p>
      </Section>
      <Section heading="Acceptable use">
        <p>
          Do not attempt to access data belonging to another organisation or to a
          colleague outside your permitted scope, interfere with the service, or use it
          to store data unrelated to performance management.
        </p>
      </Section>
      <Section heading="AI-assisted output">
        <p>
          Drafts produced by AI features are suggestions requiring human review and
          approval. Decisions about people remain the responsibility of the humans who
          approve them.
        </p>
      </Section>
      <Section heading="Availability and liability">
        <p>
          The service is provided without a specific uptime commitment unless one is
          stated in your organisation's written agreement. Nothing here limits liability
          that cannot be limited by law.
        </p>
      </Section>
      <Section heading="Contact">
        <p>
          Questions about these terms: <a className="underline" href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>.
        </p>
      </Section>
    </Shell>
  );
}

export function SupportPage() {
  return (
    <Shell title="Support">
      <Section heading="Getting help">
        <p>
          Email <a className="underline" href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>.
          Include your organisation's workspace name and, if you are reporting an error,
          what you were doing when it happened.
        </p>
      </Section>
      <Section heading="Account problems">
        <p>
          Password resets are self-service from the sign-in page. Access to a screen you
          think you should have, or a colleague's record you cannot see, is controlled by
          your role — your organisation's administrator can change it.
        </p>
      </Section>
      <Section heading="Security reports">
        <p>
          Report suspected vulnerabilities to{" "}
          <a className="underline" href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>{" "}
          with enough detail to reproduce. Please do not test against another
          organisation's data.
        </p>
      </Section>
    </Shell>
  );
}
