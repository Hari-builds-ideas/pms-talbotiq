# Talbotiq PMS — Innovation Pitch

**Enterprise-grade, AI-assisted performance management — built for the SME market, built to be trusted.**

*A vision document for leadership, partners, and customers. Everything described as shipped is in the
product today; everything forward-looking is explicitly marked **Roadmap**.*

---

## 1. The problem

Most small and mid-sized companies run performance management on spreadsheets, email threads, and
once-a-year scrambles. It quietly costs them their best people.

- **It's expensive in the wrong way.** HR and managers spend days copying data between sheets,
  chasing reviews, and reconciling ratings — time that should go to actually developing people.
- **It's inconsistent and biased.** Free-text reviews drift in quality from manager to manager. Recency
  and halo effects creep in. There's no shared standard for what "good" looks like.
- **Feedback is a once-a-year event.** By the time a review happens, the moment to coach has passed.
  There's no continuous signal, and 360° feedback — if it happens at all — isn't truly anonymous, so
  people self-censor.
- **There's no line of sight.** Who's at risk? Who's ready for the next role? Where are the succession
  gaps? Spreadsheets can't answer that, and the data is too scattered to trust.
- **Enterprise tools don't fit.** The platforms that solve this are priced and configured for large
  enterprises — overkill, overpriced, and over-complex for a 50–500 person company.

The result: SMEs either overpay for enterprise software they can't fully use, or under-invest and lose
talent they didn't see slipping away.

## 2. The vision

**Make enterprise-grade performance practice accessible to every SME — and make the AI inside it
something you can actually trust.**

Talbotiq PMS runs the full performance lifecycle — goals and KPIs, reviews, continuous and 360°
feedback, approvals, succession, career development, and analytics — in one multi-tenant platform.
AI does the heavy lifting on the work that used to eat HR's week: drafting reviews grounded in real
goal and KPI data, summarizing 360° feedback, generating job descriptions, and narrating succession
options. But a human always makes the call. The AI assists; people decide.

The aim is not "AI that replaces managers." It's **AI that gives a 100-person company the performance
discipline of a 10,000-person one — without the headcount, the consultants, or the risk.**

## 3. What makes it different

Plenty of products are bolting an LLM onto an HR form. The hard part — and our real differentiator —
isn't adding AI. It's adding AI you can put in front of employees' careers without getting burned.

### Trustworthy AI, by architecture

- **A human approves every AI output. Nothing auto-finalizes.** Every AI-generated artifact — a review
  draft, a feedback summary, a succession narrative, a job description, a career roadmap — is locked in a
  *pending human review* state until a person releases, approves, or publishes it. This "human-in-the-loop"
  gate is structural, not a setting someone can switch off.
- **360° feedback is anonymous by construction.** Reviewer identities are stripped before feedback is
  ever summarized or shown — the giver's identity never reaches an AI prompt or the recipient. A
  minimum-group-size rule prevents re-identification by inference, and a post-generation check holds any
  summary that could leak an identifier. Anonymity people can rely on is what makes honest feedback
  possible.
- **The AI assistant is bound by your permissions.** The built-in assistant answers questions in plain
  language, but it can only ever surface what the asking user is already allowed to see — it runs against
  the same role and scope checks as every other request, and any attempt to *change* something is refused.
  It cannot become a back door to data.
- **Not locked to one AI vendor.** Every AI call flows through a single internal gateway. The model
  provider is swappable by configuration — the platform runs on a leading commercial model today and can
  move to another without rewriting the product. The same gateway enforces per-customer usage budgets and
  a hard spend ceiling, so AI cost is governed, never a surprise.
- **Multi-tenant with strict isolation from day one.** Every record is scoped to its tenant at the data
  layer; one company can never see another's data — a cross-tenant request simply doesn't exist as far as
  the system is concerned. This isn't retrofitted; it's the foundation.

These five properties are the moat. They are genuinely hard to build, and they are what let a customer
trust AI with the most sensitive thing an organization has: judgments about its people.

### And the breadth to be the system of record

- **Goals & KPI engine** with enforced weighting (a person's goals, and a goal's KPIs, must sum to
  exactly 100%) and a transparent, deterministic scoring model — so scores are explainable, not a
  black box.
- **Continuous and 360° feedback** as a first-class, year-round loop, not an annual event.
- **AI-assisted job descriptions** generated from a structured brief, then human-approved and versioned.
- **Live org chart** with positions, vacancies, and reporting structure.
- **Succession planning** with a nine-box talent grid and bench-readiness views — kept name-free where it
  matters.
- **Career roadmaps** toward a target role, advisory by design (never an automated promotion).
- **Configurable approval workflows** — sequential or parallel approvers, with automatic escalation when
  someone doesn't act in time.
- **Analytics** with built-in privacy suppression, so small teams can be measured without exposing
  individuals.
- **Enterprise access controls**: role-based permissions enforced on the server, single sign-on
  (OIDC and SAML 2.0, with a safeguard that SSO can never silently escalate someone's role), multi-factor
  authentication, and a tamper-evident, insert-only audit trail.

## 4. Who it's for

**Small and mid-sized companies — their HR teams, their managers, and their employees** — that want the
rigor of an enterprise performance system without the enterprise cost and complexity.

- **The desktop Admin Hub** is the control center for HR, HRBPs, and managers: run cycles, calibrate and
  moderate, approve, configure KPIs and workflows, manage the org, and read analytics. This is shipped and
  in use against the live system today.
- **The mobile engagement hub** *(Roadmap)* is the day-to-day surface for employees and managers on the
  go — give and request feedback, track goals, complete quick 360° assessments, and approve in one tap.
  Its foundation (a shared cross-platform data/auth layer and the app scaffold) is in place; the
  employee-facing screens are the near-term build.

## 5. Why now

Two things had to be true at once for this to be possible.

**The technology arrived.** Modern LLMs can finally turn a manager's scattered notes and a quarter of KPI
data into a coherent, specific review draft — the task that used to consume HR's time is now automatable.

**But the easy version is dangerous.** Pointing a raw model at performance data gets you bias laundering,
privacy leaks, and outputs no one should trust to be final. The reason this is a real product and not a
demo is the **safety layer** — human-in-the-loop gates, structural anonymity, permission-bound AI, and
tenant isolation. That layer is the hard, unglamorous engineering, and it's already built. The moment is
now precisely because the models are ready *and* the discipline to use them responsibly has been put in
place.

## 6. Roadmap (forward-looking)

Honest about what's next, in rough order:

- **Mobile engagement hub** — ship the employee/manager mobile experience (feedback, goals, quick 360°,
  one-tap approvals) on the shared layer already extracted for it.
- **Deeper AI, proven at scale** — the AI quality work and the safety architecture are done; the next step
  is validating output quality across large, real employee populations and edge cases, and moving onto a
  production model tier with usage governance tuned for real load.
- **Richer insight surfaces** — evolve several management screens from data views into decision tools
  (command-center dashboards, guided goal setting, interactive succession and calibration).
- **Production hardening & assurance** — managed secrets, scaled hosting, formal accessibility
  certification (the automated WCAG 2.1 AA pass is in place; a full assistive-technology pass completes
  it), and third-party security testing.
- **Workflow integrations** — first-class Slack and Jira connectivity is architected and ready to light
  up with customer credentials.

None of these are required for the core promise — they deepen a platform that already runs the full
performance lifecycle end-to-end.

## 7. The vision, in one line

**Performance management that an SME can afford, an HR team can run in an afternoon, and everyone can
trust — because the AI never gets the last word, and a person always does.**
