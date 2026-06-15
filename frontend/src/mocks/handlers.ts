import { http, HttpResponse, delay } from "msw";
import type { Paginated } from "@/lib/types";
import { localId } from "@/lib/utils";
import {
  USERS,
  store,
  upgradeToFullAi,
  lockedFeatures,
  meFor,
  userById,
  CYCLES,
  workflows,
  routes,
  inboxFor,
  reviews,
  reviewTimelines,
  reviewAssessments,
  jds,
  jdVersions,
  jdRequests,
  orgTree,
  positions,
  criticalRoles,
  benchByRole,
  nineBox,
  plans,
  individualTrend,
  departmentAnalytics,
  calibration,
  auditLogs,
  integrations,
  nudgesFor,
} from "./data";
import type { AdminUser } from "@/lib/types";
import { FEATURE_META, type FeatureKey } from "@/lib/enums";

const API = "/api";
const GET_DELAY = 280;
const ACTION_DELAY = 420;

function currentUserId(request: Request): string | null {
  const auth = request.headers.get("Authorization");
  if (!auth || !auth.startsWith("Bearer mock.")) return null;
  return auth.slice("Bearer mock.".length);
}
function currentUser(request: Request): AdminUser | undefined {
  const id = currentUserId(request);
  return id ? userById(id) : undefined;
}

function unauthorized() {
  return HttpResponse.json({ detail: "Authentication required." }, { status: 401 });
}
function forbidden(detail = "You don't have permission to do this.") {
  return HttpResponse.json({ detail }, { status: 403 });
}
function notFound(detail = "Not found.") {
  return HttpResponse.json({ detail }, { status: 404 });
}
function conflict(detail: string, code = "ILLEGAL_TRANSITION") {
  return HttpResponse.json({ detail, code }, { status: 409 });
}
function domain(detail: string, code: string) {
  return HttpResponse.json({ detail, code }, { status: 422 });
}
function unavailable(detail = "AI is not configured yet.") {
  return HttpResponse.json({ detail }, { status: 503 });
}

function paginate<T>(request: Request, items: T[]): Paginated<T> {
  const url = new URL(request.url);
  const page = Math.max(1, Number(url.searchParams.get("page") ?? 1));
  const pageSize = Math.min(200, Math.max(1, Number(url.searchParams.get("page_size") ?? 50)));
  const start = (page - 1) * pageSize;
  const results = items.slice(start, start + pageSize);
  return {
    count: items.length,
    next: start + pageSize < items.length ? `${url.pathname}?page=${page + 1}` : null,
    previous: page > 1 ? `${url.pathname}?page=${page - 1}` : null,
    results,
  };
}

const rank: Record<string, number> = { EMPLOYEE: 0, MANAGER: 1, HRBP: 2, ADMIN: 3 };
function atLeast(role: string | undefined, min: string): boolean {
  return role ? rank[role] >= rank[min] : false;
}

export const handlers = [
  // ---- Auth ----------------------------------------------------------------
  http.post(`${API}/auth/login`, async ({ request }) => {
    await delay(ACTION_DELAY);
    const body = (await request.json()) as { email?: string };
    const user = USERS.find(
      (u) => u.email.toLowerCase() === (body.email ?? "").toLowerCase(),
    );
    if (!user) {
      return HttpResponse.json({ detail: "Invalid credentials." }, { status: 401 });
    }
    if (user.mfa_enabled) {
      return HttpResponse.json({ mfa_required: true, challenge: user.id });
    }
    return HttpResponse.json({ access: `mock.${user.id}`, refresh: `mockr.${user.id}` });
  }),

  http.post(`${API}/auth/mfa/challenge`, async ({ request }) => {
    await delay(ACTION_DELAY);
    const body = (await request.json()) as { challenge?: string; code?: string };
    if (!body.code || !/^\d{6}$/.test(body.code)) {
      return HttpResponse.json({ detail: "Invalid code." }, { status: 401 });
    }
    const id = body.challenge ?? "u-1";
    return HttpResponse.json({ access: `mock.${id}`, refresh: `mockr.${id}` });
  }),

  http.post(`${API}/auth/mfa/enroll`, async () => {
    await delay(GET_DELAY);
    return HttpResponse.json({
      secret: "JBSWY3DPEHPK3PXP",
      otpauth_url: "otpauth://totp/Talbotiq:demo?secret=JBSWY3DPEHPK3PXP&issuer=Talbotiq",
    });
  }),
  http.post(`${API}/auth/mfa/enroll/confirm`, async () => {
    await delay(ACTION_DELAY);
    return HttpResponse.json({ ok: true });
  }),

  http.post(`${API}/auth/token/refresh`, async ({ request }) => {
    const body = (await request.json()) as { refresh?: string };
    if (!body.refresh || !body.refresh.startsWith("mockr.")) {
      return HttpResponse.json({ detail: "Invalid refresh." }, { status: 401 });
    }
    const id = body.refresh.slice("mockr.".length);
    return HttpResponse.json({ access: `mock.${id}`, refresh: `mockr.${id}` });
  }),

  http.get(`${API}/auth/me`, async ({ request }) => {
    await delay(GET_DELAY);
    const id = currentUserId(request);
    const me = id ? meFor(id) : undefined;
    if (!me) return unauthorized();
    return HttpResponse.json(me);
  }),

  http.post(`${API}/auth/logout`, async () => {
    await delay(120);
    return HttpResponse.json({ ok: true });
  }),

  // ---- Billing -------------------------------------------------------------
  http.get(`${API}/billing/my-features`, async ({ request }) => {
    await delay(GET_DELAY);
    if (!currentUser(request)) return unauthorized();
    return HttpResponse.json(store.featureFlags);
  }),
  http.get(`${API}/billing/feature-flags`, async ({ request }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (u.role !== "ADMIN") return forbidden();
    return HttpResponse.json(store.featureFlags);
  }),
  http.get(`${API}/billing/entitlement`, async ({ request }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (u.role !== "ADMIN") return forbidden();
    return HttpResponse.json(store.entitlement);
  }),
  http.get(`${API}/billing/upgrade-prompt`, async ({ request }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (u.role !== "ADMIN") return forbidden();
    const locked = lockedFeatures();
    return HttpResponse.json({
      current_packs: store.entitlement.feature_packs,
      tier_label: store.entitlement.tier_label,
      feature_flags: store.featureFlags,
      locked_features: locked,
      upgrade: {
        pack: "FULL_AI",
        would_unlock: locked.filter((f) => FEATURE_META[f as FeatureKey]?.pack === "FULL_AI"),
        note: "Conceptual only — no pricing or payment is captured.",
      },
    });
  }),
  http.post(`${API}/billing/upgrade`, async ({ request }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (u.role !== "ADMIN") return forbidden();
    return HttpResponse.json(upgradeToFullAi());
  }),
  http.patch(`${API}/billing/seats`, async ({ request }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (u.role !== "ADMIN") return forbidden();
    const body = (await request.json()) as { seat_count?: number };
    if (body.seat_count == null || body.seat_count < 0 || !Number.isInteger(body.seat_count)) {
      return domain("Seat count must be a non-negative integer.", "INVALID_SEATS");
    }
    store.entitlement = { ...store.entitlement, seat_count: body.seat_count };
    return HttpResponse.json(store.entitlement);
  }),

  // ---- Admin ---------------------------------------------------------------
  http.get(`${API}/admin/users`, async ({ request }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (u.role !== "ADMIN") return forbidden();
    return HttpResponse.json(USERS);
  }),
  http.post(`${API}/admin/users`, async ({ request }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (u.role !== "ADMIN") return forbidden();
    const body = (await request.json()) as Partial<AdminUser> & { password?: string };
    if (!body.email) return domain("Email is required.", "EMAIL_TAKEN");
    if (USERS.some((x) => x.email.toLowerCase() === body.email!.toLowerCase())) {
      return domain("A user with that email already exists.", "EMAIL_TAKEN");
    }
    if (!body.role || !rank[body.role]) {
      if (body.role !== "EMPLOYEE") return domain("Unknown role.", "UNKNOWN_ROLE");
    }
    const created: AdminUser = {
      id: localId("u"),
      email: body.email,
      display_name: body.display_name ?? null,
      display: body.display_name || body.email,
      role: (body.role as AdminUser["role"]) ?? "EMPLOYEE",
      manager: body.manager ?? null,
      is_active: true,
      mfa_enabled: false,
    };
    USERS.push(created);
    return HttpResponse.json(created, { status: 201 });
  }),
  http.post(`${API}/admin/users/:id/role`, async ({ request, params }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (u.role !== "ADMIN") return forbidden();
    const target = userById(params.id as string);
    if (!target) return notFound("User not found.");
    const body = (await request.json()) as { role?: AdminUser["role"] };
    if (!body.role || rank[body.role] === undefined) return domain("Unknown role.", "UNKNOWN_ROLE");
    target.role = body.role;
    return HttpResponse.json(target);
  }),
  http.post(`${API}/admin/users/:id/deactivate`, async ({ request, params }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (u.role !== "ADMIN") return forbidden();
    const target = userById(params.id as string);
    if (!target) return notFound("User not found.");
    target.is_active = false;
    return HttpResponse.json(target);
  }),
  http.post(`${API}/admin/users/:id/reactivate`, async ({ request, params }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (u.role !== "ADMIN") return forbidden();
    const target = userById(params.id as string);
    if (!target) return notFound("User not found.");
    target.is_active = true;
    return HttpResponse.json(target);
  }),
  http.post(`${API}/admin/users/:id/reporting-line`, async ({ request, params }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (u.role !== "ADMIN") return forbidden();
    const target = userById(params.id as string);
    if (!target) return notFound("User not found.");
    const body = (await request.json()) as { manager?: string | null };
    if (body.manager === target.id) return domain("A user cannot report to themselves.", "REPORTING_CYCLE");
    // simple cycle check: manager must not be a (transitive) report of target
    let cursor = body.manager ? userById(body.manager) : undefined;
    const guard = new Set<string>();
    while (cursor) {
      if (cursor.id === target.id) return domain("That reassignment would create a reporting cycle.", "REPORTING_CYCLE");
      if (guard.has(cursor.id)) break;
      guard.add(cursor.id);
      cursor = cursor.manager ? userById(cursor.manager) : undefined;
    }
    target.manager = body.manager ?? null;
    return HttpResponse.json(target);
  }),
  http.post(`${API}/admin/users/:id/display-name`, async ({ request, params }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (u.role !== "ADMIN") return forbidden();
    const target = userById(params.id as string);
    if (!target) return notFound("User not found.");
    const body = (await request.json()) as { display_name?: string | null };
    const name = body.display_name?.trim() || null;
    target.display_name = name;
    target.display = name || target.email;
    return HttpResponse.json(target);
  }),
  http.get(`${API}/admin/tenant-config`, async ({ request }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (u.role !== "ADMIN") return forbidden();
    return HttpResponse.json(store.tenantConfig);
  }),
  http.put(`${API}/admin/tenant-config`, async ({ request }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (u.role !== "ADMIN") return forbidden();
    const body = (await request.json()) as { settings?: Record<string, unknown> };
    store.tenantConfig = { ...store.tenantConfig, settings: body.settings ?? {} };
    return HttpResponse.json(store.tenantConfig);
  }),

  // ---- Approvals -----------------------------------------------------------
  http.get(`${API}/approvals/inbox`, async ({ request }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "MANAGER")) return forbidden();
    return HttpResponse.json(inboxFor(u.role));
  }),
  http.get(`${API}/approvals/workflows`, async ({ request }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "HRBP")) return forbidden();
    return HttpResponse.json(workflows);
  }),
  http.post(`${API}/approvals/workflows`, async ({ request }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "HRBP")) return forbidden();
    const body = (await request.json()) as Partial<(typeof workflows)[number]>;
    const created = {
      id: localId("wf"),
      name: body.name ?? "Untitled workflow",
      artifact_type: body.artifact_type ?? "review",
      mode: body.mode ?? "SEQUENTIAL",
      active: false,
      steps: body.steps ?? [],
    } as (typeof workflows)[number];
    workflows.push(created);
    return HttpResponse.json(created, { status: 201 });
  }),
  http.post(`${API}/approvals/workflows/:id/activate`, async ({ request, params }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "HRBP")) return forbidden();
    const wf = workflows.find((w) => w.id === params.id);
    if (!wf) return notFound();
    const clash = workflows.find((w) => w.artifact_type === wf.artifact_type && w.active && w.id !== wf.id);
    if (clash) return conflict(`Another workflow is already active for "${wf.artifact_type}".`, "WORKFLOW_ACTIVE_CONFLICT");
    wf.active = true;
    return HttpResponse.json(wf);
  }),
  http.post(`${API}/approvals/workflows/:id/deactivate`, async ({ request, params }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "HRBP")) return forbidden();
    const wf = workflows.find((w) => w.id === params.id);
    if (!wf) return notFound();
    wf.active = false;
    return HttpResponse.json(wf);
  }),
  http.get(`${API}/approvals/routes/:id`, async ({ request, params }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    const route = routes.find((r) => r.id === params.id);
    if (!route) return notFound();
    return HttpResponse.json(route);
  }),
  http.get(`${API}/approvals/routes`, async ({ request }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    const url = new URL(request.url);
    const at = url.searchParams.get("artifact_type");
    const aid = url.searchParams.get("artifact_id");
    const matched = routes.filter(
      (r) => (!at || r.artifact_type === at) && (!aid || r.artifact_id === aid),
    );
    return HttpResponse.json(matched);
  }),
  http.post(`${API}/approvals/steps/:id/approve`, async ({ request, params }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "MANAGER")) return forbidden();
    const body = (await request.json().catch(() => ({}))) as { comment?: string };
    const route = routes.find((r) => r.step_instances.some((s) => s.id === params.id));
    if (!route) return notFound();
    const step = route.step_instances.find((s) => s.id === params.id)!;
    if (step.status !== "PENDING") return conflict("That step was already decided.", "STEP_DECIDED");
    if (route.mode === "SEQUENTIAL") {
      const active = route.step_instances.find((s) => s.status === "PENDING");
      if (active?.id !== step.id) return conflict("This step isn't active yet.", "STEP_OUT_OF_ORDER");
    }
    step.status = "APPROVED";
    step.decided_by = u.id;
    step.decided_at = new Date().toISOString();
    step.approver = u.id;
    step.comment = body.comment ?? "";
    const requiredPending = route.step_instances.filter((s) => s.status === "PENDING");
    if (requiredPending.length === 0) route.status = "APPROVED";
    return HttpResponse.json(route);
  }),
  http.post(`${API}/approvals/steps/:id/reject`, async ({ request, params }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "MANAGER")) return forbidden();
    const body = (await request.json().catch(() => ({}))) as { comment?: string };
    if (!body.comment || !body.comment.trim()) {
      return domain("A reason is required to reject.", "REJECTION_REASON_REQUIRED");
    }
    const route = routes.find((r) => r.step_instances.some((s) => s.id === params.id));
    if (!route) return notFound();
    const step = route.step_instances.find((s) => s.id === params.id)!;
    if (step.status !== "PENDING") return conflict("That step was already decided.", "STEP_DECIDED");
    step.status = "REJECTED";
    step.decided_by = u.id;
    step.decided_at = new Date().toISOString();
    step.approver = u.id;
    step.comment = body.comment;
    route.status = "REJECTED";
    return HttpResponse.json(route);
  }),

  // ---- Cycles --------------------------------------------------------------
  http.get(`${API}/cycles/`, async ({ request }) => {
    await delay(GET_DELAY);
    if (!currentUser(request)) return unauthorized();
    return HttpResponse.json(CYCLES);
  }),

  // ---- Reviews -------------------------------------------------------------
  http.get(`${API}/reviews/`, async ({ request }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "MANAGER")) return forbidden();
    const url = new URL(request.url);
    const cycle = url.searchParams.get("cycle");
    const filtered = reviews.filter((r) => !cycle || r.cycle === cycle);
    return HttpResponse.json(paginate(request, filtered));
  }),
  http.post(`${API}/reviews/`, async ({ request }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "MANAGER")) return forbidden();
    const body = (await request.json()) as { employee?: string; cycle?: string };
    const created = {
      id: localId("rv"), employee: body.employee ?? "u-2", reviewer: u.id, cycle: body.cycle ?? "cy-1",
      state: "DRAFT" as const, draft_body: "", final_body: "", human_reviewer: null, approved_at: null,
      finalized_at: null, rejected_reason: null, source: "MANUAL" as const, confidence_score: null,
      citations: null, approval_route: null,
    };
    reviews.unshift(created);
    return HttpResponse.json(created, { status: 201 });
  }),
  http.get(`${API}/reviews/:id`, async ({ request, params }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    const r = reviews.find((x) => x.id === params.id);
    if (!r) return notFound();
    return HttpResponse.json(r);
  }),
  http.get(`${API}/reviews/:id/timeline`, async ({ request, params }) => {
    await delay(GET_DELAY);
    if (!currentUser(request)) return unauthorized();
    return HttpResponse.json(reviewTimelines[params.id as string] ?? []);
  }),
  http.get(`${API}/reviews/:id/assessments`, async ({ request, params }) => {
    await delay(GET_DELAY);
    if (!currentUser(request)) return unauthorized();
    return HttpResponse.json(reviewAssessments[params.id as string] ?? []);
  }),
  ...reviewTransition("start-edit", (r) => {
    if (!["DRAFT", "PENDING_HUMAN_REVIEW", "REJECTED"].includes(r.state)) return conflict("Can't edit from the current state.", "ILLEGAL_TRANSITION");
    r.state = "EDITING";
    return null;
  }),
  ...reviewTransition("submit", (r, body) => {
    if (r.state !== "EDITING") return conflict("Submit is only valid while editing.", "ILLEGAL_TRANSITION");
    if (body?.draft_body) r.draft_body = body.draft_body;
    r.state = "PENDING_HUMAN_REVIEW";
    return null;
  }),
  ...reviewTransition("save-draft", (r, body) => {
    if (body?.draft_body != null) r.draft_body = body.draft_body;
    return null;
  }),
  ...reviewTransition("approve", (r, _body, u) => {
    if (r.state !== "PENDING_HUMAN_REVIEW") return conflict("Approve is only valid from pending review.", "ILLEGAL_TRANSITION");
    r.state = "APPROVED";
    r.human_reviewer = u.id;
    r.approved_at = new Date().toISOString();
    if (!r.final_body) r.final_body = r.draft_body;
    return null;
  }),
  ...reviewTransition("reject", (r, body) => {
    if (r.state !== "PENDING_HUMAN_REVIEW") return conflict("Reject is only valid from pending review.", "ILLEGAL_TRANSITION");
    if (!body?.reason || !body.reason.trim()) return domain("A rejection reason is required.", "REJECTION_REASON_REQUIRED");
    r.state = "REJECTED";
    r.rejected_reason = body.reason;
    return null;
  }),
  ...reviewTransition("finalize", (r) => {
    if (r.state !== "APPROVED") return domain("Finalize requires an approved review.", "HITL_APPROVAL_REQUIRED");
    r.state = "FINALIZED";
    r.finalized_at = new Date().toISOString();
    return null;
  }),
  http.post(`${API}/reviews/:id/request-ai-draft`, async ({ request }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "MANAGER")) return forbidden();
    if (!store.featureFlags.agent1) return forbidden("The Review Assistant (Agent 1) is a Full AI feature.");
    // Agent 1 seam not configured in the mock world → 503 (manual path still works).
    return unavailable("The Review Assistant isn't configured yet — draft manually for now.");
  }),

  // ---- JD ------------------------------------------------------------------
  http.get(`${API}/jd/`, async ({ request }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    const visible = atLeast(u.role, "HRBP") ? jds : jds.filter((j) => j.status === "PUBLISHED");
    return HttpResponse.json(paginate(request, visible));
  }),
  http.post(`${API}/jd/`, async ({ request }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "HRBP")) return forbidden();
    const body = (await request.json()) as { title?: string; level?: string; department?: string };
    const id = localId("jd");
    const created = { id, title: body.title ?? "Untitled", level: body.level ?? "L1", department: body.department ?? "", status: "DRAFT" as const, source: "MANUAL" as const, current_version: null, created_by: u.id, approval_route: null };
    jds.unshift(created);
    jdVersions[id] = [{ id: localId("jdv"), version_number: 1, is_published: false, confidence_score: null, citations: null, body: { summary: "", responsibilities: [], must_haves: [], nice_to_haves: [] } }];
    return HttpResponse.json(created, { status: 201 });
  }),
  http.get(`${API}/jd/requests`, async ({ request }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    return HttpResponse.json(paginate(request, jdRequests));
  }),
  http.post(`${API}/jd/requests`, async ({ request }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    const body = (await request.json()) as { title?: string; level?: string; notes?: string };
    const created = { id: localId("jr"), requested_by: u.id, title: body.title ?? "", level: body.level ?? "", notes: body.notes ?? "", status: "OPEN" as const };
    jdRequests.unshift(created);
    return HttpResponse.json(created, { status: 201 });
  }),
  http.post(`${API}/jd/requests/:id/fulfil`, async ({ request, params }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u || !atLeast(u.role, "HRBP")) return u ? forbidden() : unauthorized();
    const req = jdRequests.find((r) => r.id === params.id);
    if (!req) return notFound();
    req.status = "FULFILLED";
    return HttpResponse.json(req);
  }),
  http.post(`${API}/jd/requests/:id/decline`, async ({ request, params }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u || !atLeast(u.role, "HRBP")) return u ? forbidden() : unauthorized();
    const req = jdRequests.find((r) => r.id === params.id);
    if (!req) return notFound();
    req.status = "DECLINED";
    return HttpResponse.json(req);
  }),
  http.get(`${API}/jd/:id`, async ({ request, params }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    const jd = jds.find((j) => j.id === params.id);
    if (!jd) return notFound();
    if (jd.status !== "PUBLISHED" && !atLeast(u.role, "HRBP")) return notFound();
    return HttpResponse.json(jd);
  }),
  http.get(`${API}/jd/:id/versions`, async ({ request, params }) => {
    await delay(GET_DELAY);
    if (!currentUser(request)) return unauthorized();
    return HttpResponse.json(jdVersions[params.id as string] ?? []);
  }),
  ...jdTransition("save-draft", () => null),
  ...jdTransition("submit", (jd) => {
    const v = (jdVersions[jd.id] ?? [])[0];
    if (!jd.title || !jd.level || !v?.body.summary || v.body.responsibilities.length === 0 || v.body.must_haves.length === 0) {
      return domain("Title, level and a body (summary, responsibilities, must-haves) are required.", "INVALID_JD_INPUT");
    }
    if (jd.status !== "DRAFT") return conflict("Submit is only valid from draft.", "ILLEGAL_JD_TRANSITION");
    jd.status = "PENDING_HUMAN_REVIEW";
    return null;
  }),
  ...jdTransition("approve", (jd) => {
    if (jd.status !== "PENDING_HUMAN_REVIEW") return conflict("Approve is only valid from pending review.", "ILLEGAL_JD_TRANSITION");
    jd.status = "PUBLISHED";
    const versions = jdVersions[jd.id] ?? [];
    if (versions[0]) { versions[0].is_published = true; jd.current_version = versions[0].id ?? null; }
    return null;
  }),
  ...jdTransition("revise", (jd) => {
    if (jd.status !== "PUBLISHED") return conflict("Only a published JD can be revised.", "ILLEGAL_JD_TRANSITION");
    jd.status = "DRAFT";
    const versions = jdVersions[jd.id] ?? [];
    const next = (versions[0]?.version_number ?? 0) + 1;
    versions.unshift({ id: localId("jdv"), version_number: next, is_published: false, confidence_score: null, citations: null, body: { ...(versions[0]?.body ?? { summary: "", responsibilities: [], must_haves: [], nice_to_haves: [] }) } });
    jdVersions[jd.id] = versions;
    return null;
  }),
  ...jdTransition("archive", (jd) => { jd.status = "ARCHIVED"; return null; }),
  http.post(`${API}/jd/:id/generate`, async ({ request, params }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "HRBP")) return forbidden();
    if (!store.featureFlags.jd_generator) return forbidden("The JD generator is a Full AI feature.");
    const jd = jds.find((j) => j.id === params.id);
    if (!jd) return notFound();
    return unavailable("The JD generator isn't configured yet — author manually for now.");
  }),

  // ---- Org -----------------------------------------------------------------
  http.get(`${API}/org/tree`, async ({ request }) => {
    await delay(GET_DELAY);
    if (!currentUser(request)) return unauthorized();
    return HttpResponse.json(orgTree());
  }),
  http.get(`${API}/org/search`, async ({ request }) => {
    await delay(GET_DELAY);
    if (!currentUser(request)) return unauthorized();
    const url = new URL(request.url);
    const q = (url.searchParams.get("q") ?? "").toLowerCase();
    const matched = USERS.filter(
      (u) => u.is_active && (u.display.toLowerCase().includes(q) || u.email.toLowerCase().includes(q)),
    ).map((u) => ({ id: u.id, email: u.email, display_name: u.display_name, display: u.display, role: u.role, title: "" }));
    return HttpResponse.json(paginate(request, matched));
  }),
  http.get(`${API}/org/vacancies`, async ({ request }) => {
    await delay(GET_DELAY);
    if (!currentUser(request)) return unauthorized();
    return HttpResponse.json(positions.filter((p) => p.status === "OPEN"));
  }),
  http.get(`${API}/org/positions`, async ({ request }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    return HttpResponse.json(paginate(request, positions));
  }),
  http.post(`${API}/org/positions`, async ({ request }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u || !atLeast(u.role, "HRBP")) return u ? forbidden() : unauthorized();
    const body = (await request.json()) as { title?: string; reports_to?: string | null; department?: string };
    const created = { id: localId("p"), title: body.title ?? "Untitled", reports_to: body.reports_to ?? null, department: body.department ?? "", status: "OPEN" as const, filled_by: null, published_jd: null, opened_at: new Date().toISOString(), filled_at: null };
    positions.unshift(created);
    return HttpResponse.json(created, { status: 201 });
  }),
  http.post(`${API}/org/positions/:id/fill`, async ({ request, params }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u || !atLeast(u.role, "HRBP")) return u ? forbidden() : unauthorized();
    const p = positions.find((x) => x.id === params.id);
    if (!p) return notFound();
    if (p.status === "FILLED") return conflict("That position is already filled.", "POSITION_FILLED");
    const body = (await request.json()) as { filled_by?: string };
    p.status = "FILLED"; p.filled_by = body.filled_by ?? null; p.filled_at = new Date().toISOString();
    return HttpResponse.json(p);
  }),
  http.post(`${API}/org/positions/:id/close`, async ({ request, params }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u || !atLeast(u.role, "HRBP")) return u ? forbidden() : unauthorized();
    const p = positions.find((x) => x.id === params.id);
    if (!p) return notFound();
    p.status = "CLOSED";
    return HttpResponse.json(p);
  }),
  http.post(`${API}/org/positions/:id/link-jd`, async ({ request, params }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u || !atLeast(u.role, "HRBP")) return u ? forbidden() : unauthorized();
    const p = positions.find((x) => x.id === params.id);
    if (!p) return notFound();
    const body = (await request.json()) as { jd?: string };
    const jd = jds.find((j) => j.id === body.jd);
    if (!jd) return notFound("JD not found.");
    if (jd.status !== "PUBLISHED") return domain("Only a published JD can be linked.", "JD_NOT_PUBLISHED");
    p.published_jd = jd.id;
    return HttpResponse.json(p);
  }),
  http.post(`${API}/org/positions/:id/unlink-jd`, async ({ request, params }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u || !atLeast(u.role, "HRBP")) return u ? forbidden() : unauthorized();
    const p = positions.find((x) => x.id === params.id);
    if (!p) return notFound();
    p.published_jd = null;
    return HttpResponse.json(p);
  }),
  http.post(`${API}/org/reassign`, async ({ request }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u || !atLeast(u.role, "HRBP")) return u ? forbidden() : unauthorized();
    const body = (await request.json()) as { employee?: string; manager?: string | null };
    const emp = userById(body.employee);
    if (!emp) return notFound("Employee not found.");
    if (body.manager === emp.id) return domain("A user cannot report to themselves.", "REPORTING_CYCLE");
    let cursor = body.manager ? userById(body.manager) : undefined;
    const guard = new Set<string>();
    while (cursor) {
      if (cursor.id === emp.id) return domain("That reassignment would create a reporting cycle.", "REPORTING_CYCLE");
      if (guard.has(cursor.id)) break;
      guard.add(cursor.id);
      cursor = cursor.manager ? userById(cursor.manager) : undefined;
    }
    emp.manager = body.manager ?? null;
    return HttpResponse.json({ ok: true });
  }),
  http.get(`${API}/org/people/:id`, async ({ request, params }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    const target = userById(params.id as string);
    if (!target || !target.is_active) return notFound();
    const mgr = target.manager ? userById(target.manager) : null;
    const filled = positions.filter((p) => p.filled_by === target.id);
    return HttpResponse.json({
      id: target.id, email: target.email, display_name: target.display_name, display: target.display, role: target.role,
      title: filled[0]?.title ?? "",
      manager: mgr ? { id: mgr.id, email: mgr.email, display: mgr.display } : null,
      direct_reports: USERS.filter((x) => x.manager === target.id && x.is_active).length,
      filled_positions: filled.map((p) => ({ id: p.id, title: p.title, department: p.department, published_jd: p.published_jd })),
      published_jds: filled.map((p) => p.published_jd).filter(Boolean),
    });
  }),

  // ---- Succession (employees → 404 everywhere) -----------------------------
  http.get(`${API}/succession/dashboard`, async ({ request }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "MANAGER")) return notFound();
    return HttpResponse.json({ critical_roles: criticalRoles.filter((c) => c.status === "ACTIVE") });
  }),
  http.get(`${API}/succession/critical-roles`, async ({ request }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "MANAGER")) return notFound();
    return HttpResponse.json(paginate(request, criticalRoles));
  }),
  http.post(`${API}/succession/critical-roles`, async ({ request }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "MANAGER")) return notFound();
    if (!atLeast(u.role, "HRBP")) return forbidden("Marking a critical role requires HRBP+.");
    const body = (await request.json()) as Partial<(typeof criticalRoles)[number]>;
    const created = { id: localId("cr"), name: body.name ?? "Untitled role", position: body.position ?? null, incumbent: body.incumbent ?? null, criticality: body.criticality ?? "HIGH", knowledge_risk: body.knowledge_risk ?? "MEDIUM", risk_notes: body.risk_notes ?? "", status: "ACTIVE" as const, coverage_status: "RED" as const, published_plan: null };
    criticalRoles.unshift(created);
    benchByRole[created.id] = [];
    return HttpResponse.json(created, { status: 201 });
  }),
  http.post(`${API}/succession/critical-roles/:id/knowledge-risk`, async ({ request, params }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "MANAGER")) return notFound();
    if (!atLeast(u.role, "HRBP")) return forbidden();
    const cr = criticalRoles.find((c) => c.id === params.id);
    if (!cr) return notFound();
    const body = (await request.json()) as { knowledge_risk?: CriticalRoleRisk; risk_notes?: string };
    if (body.knowledge_risk) cr.knowledge_risk = body.knowledge_risk;
    if (body.risk_notes != null) cr.risk_notes = body.risk_notes;
    return HttpResponse.json(cr);
  }),
  http.post(`${API}/succession/critical-roles/:id/archive`, async ({ request, params }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "HRBP")) return u && atLeast(u.role, "MANAGER") ? forbidden() : notFound();
    const cr = criticalRoles.find((c) => c.id === params.id);
    if (!cr) return notFound();
    cr.status = "ARCHIVED";
    return HttpResponse.json(cr);
  }),
  http.get(`${API}/succession/critical-roles/:id/bench`, async ({ request, params }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "MANAGER")) return notFound();
    return HttpResponse.json(paginate(request, benchByRole[params.id as string] ?? []));
  }),
  http.post(`${API}/succession/critical-roles/:id/bench`, async ({ request, params }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "MANAGER")) return notFound();
    const body = (await request.json()) as { candidate?: string; notes?: string };
    const created = { id: localId("bc"), candidate: body.candidate ?? "u-2", readiness: "DEVELOPING" as const, readiness_overridden: false, notes: body.notes ?? "" };
    (benchByRole[params.id as string] ??= []).push(created);
    return HttpResponse.json(created, { status: 201 });
  }),
  http.post(`${API}/succession/bench/:id/readiness`, async ({ request, params }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "MANAGER")) return notFound();
    const body = (await request.json()) as { readiness?: BenchReadiness };
    for (const list of Object.values(benchByRole)) {
      const bc = list.find((b) => b.id === params.id);
      if (bc) { if (body.readiness) { bc.readiness = body.readiness; bc.readiness_overridden = true; } return HttpResponse.json(bc); }
    }
    return notFound();
  }),
  http.post(`${API}/succession/critical-roles/:id/generate`, async ({ request, params }) => {
    await delay(ACTION_DELAY + 300);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "MANAGER")) return notFound();
    if (!atLeast(u.role, "HRBP")) return forbidden("Generating a plan requires HRBP+.");
    const cr = criticalRoles.find((c) => c.id === params.id);
    if (!cr) return notFound();
    const id = localId("sp");
    const bench = benchByRole[cr.id] ?? [];
    const coverage = bench.some((b) => b.readiness === "READY_NOW") ? "GREEN" : bench.length ? "AMBER" : "RED";
    const plan = {
      id, status: "PENDING_HUMAN_REVIEW" as const, coverage_status: coverage as "RED" | "AMBER" | "GREEN", source: "DETERMINISTIC" as const, confidence_score: null,
      ranked_bench: bench.map((b) => ({ candidate: b.candidate, readiness: b.readiness })),
      red_flags: coverage === "RED" ? ["INADEQUATE_COVERAGE"] : [],
      action_items: [] as Array<{ text: string; added_by?: string }>,
    };
    plans[id] = plan;
    cr.published_plan = null;
    return HttpResponse.json(plan, { status: 201 });
  }),
  http.get(`${API}/succession/nine-box`, async ({ request }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "MANAGER")) return notFound();
    const url = new URL(request.url);
    const cycle = url.searchParams.get("cycle");
    return HttpResponse.json(paginate(request, nineBox.filter((n) => !cycle || n.cycle === cycle)));
  }),
  http.post(`${API}/succession/nine-box`, async ({ request }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "MANAGER")) return notFound();
    const body = (await request.json()) as { employee?: string; cycle?: string; potential_band?: BenchBand };
    const perf = nineBox.find((n) => n.employee === body.employee)?.performance_band ?? "MEDIUM";
    const bandIndex: Record<string, number> = { LOW: 0, MEDIUM: 1, HIGH: 2 };
    const pot = body.potential_band ?? "MEDIUM";
    const box = bandIndex[perf] + bandIndex[pot] * 3 + 1;
    const existing = nineBox.find((n) => n.employee === body.employee && n.cycle === body.cycle);
    if (existing) { existing.potential_band = pot; existing.box = box; return HttpResponse.json(existing); }
    const created = { id: localId("nb"), employee: body.employee ?? "u-2", cycle: body.cycle ?? "cy-1", performance_band: perf, potential_band: pot, box };
    nineBox.push(created);
    return HttpResponse.json(created, { status: 201 });
  }),
  http.get(`${API}/succession/plans/:id`, async ({ request, params }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "MANAGER")) return notFound();
    const plan = plans[params.id as string];
    if (!plan) return notFound();
    return HttpResponse.json(plan);
  }),
  http.post(`${API}/succession/plans/:id/action-item`, async ({ request, params }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "HRBP")) return u && atLeast(u.role, "MANAGER") ? forbidden() : notFound();
    const plan = plans[params.id as string];
    if (!plan) return notFound();
    if (plan.status !== "PENDING_HUMAN_REVIEW") return conflict("Action items can only be added while pending.", "ILLEGAL_PLAN_TRANSITION");
    const body = (await request.json()) as { text?: string };
    plan.action_items.push({ text: body.text ?? "", added_by: u.id });
    return HttpResponse.json(plan);
  }),
  http.post(`${API}/succession/plans/:id/publish`, async ({ request, params }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "HRBP")) return u && atLeast(u.role, "MANAGER") ? forbidden() : notFound();
    const plan = plans[params.id as string];
    if (!plan) return notFound();
    if (plan.status !== "PENDING_HUMAN_REVIEW") return conflict(`Cannot publish a plan in status ${plan.status}.`, "ILLEGAL_PLAN_TRANSITION");
    plan.status = "PUBLISHED";
    const cr = criticalRoles.find((c) => (benchByRole[c.id] ?? []).length >= 0 && c.published_plan === null && c.coverage_status === plan.coverage_status) ?? criticalRoles[0];
    if (cr) cr.published_plan = plan.id;
    return HttpResponse.json(plan);
  }),
  http.post(`${API}/succession/plans/:id/enrich`, async ({ request }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "HRBP")) return u && atLeast(u.role, "MANAGER") ? forbidden() : notFound();
    if (!store.featureFlags.agent4) return forbidden("The Succession Analyzer (Agent 4) is a Full AI feature.");
    return unavailable("The Succession Analyzer isn't configured yet.");
  }),

  // ---- Analytics -----------------------------------------------------------
  http.get(`${API}/analytics/individual`, async ({ request }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    const url = new URL(request.url);
    const employee = url.searchParams.get("employee") ?? u.id;
    if (u.role === "EMPLOYEE" && employee !== u.id) return notFound();
    return HttpResponse.json(individualTrend(employee));
  }),
  http.get(`${API}/analytics/department`, async ({ request }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (u.role === "EMPLOYEE") return forbidden();
    const url = new URL(request.url);
    const head = url.searchParams.get("head");
    const cycle = url.searchParams.get("cycle");
    if (!cycle) return HttpResponse.json({ detail: "cycle is required.", cycle: ["This field is required."] }, { status: 400 });
    return HttpResponse.json(departmentAnalytics(head ?? u.id, cycle));
  }),
  http.get(`${API}/analytics/calibration`, async ({ request }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "HRBP")) return forbidden();
    const url = new URL(request.url);
    const cycle = url.searchParams.get("cycle");
    if (!cycle) return HttpResponse.json({ detail: "cycle is required.", cycle: ["This field is required."] }, { status: 400 });
    return HttpResponse.json(calibration(cycle));
  }),

  // ---- Audit ---------------------------------------------------------------
  http.get(`${API}/audit/logs`, async ({ request }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!atLeast(u.role, "HRBP")) return forbidden();
    const url = new URL(request.url);
    const actor = url.searchParams.get("actor");
    const action = url.searchParams.get("action");
    const targetType = url.searchParams.get("target_type");
    let items = auditLogs;
    if (actor) items = items.filter((l) => l.actor === actor);
    if (action) items = items.filter((l) => l.action.includes(action));
    if (targetType) items = items.filter((l) => l.target_type === targetType);
    return HttpResponse.json(paginate(request, items));
  }),

  // ---- Integrations --------------------------------------------------------
  http.get(`${API}/integrations/`, async ({ request }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (u.role !== "ADMIN") return forbidden();
    return HttpResponse.json(integrations);
  }),
  http.get(`${API}/integrations/:kind`, async ({ request, params }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (u.role !== "ADMIN") return forbidden();
    const kind = String(params.kind).toUpperCase();
    if (kind !== "JIRA" && kind !== "SLACK") return HttpResponse.json({ detail: "Unknown integration kind." }, { status: 400 });
    const found = integrations.find((i) => i.kind === kind);
    if (!found) return notFound("Not configured.");
    return HttpResponse.json(found);
  }),
  http.put(`${API}/integrations/:kind`, async ({ request, params }) => {
    await delay(ACTION_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (u.role !== "ADMIN") return forbidden();
    const kind = String(params.kind).toUpperCase();
    if (kind !== "JIRA" && kind !== "SLACK") return HttpResponse.json({ detail: "Unknown integration kind." }, { status: 400 });
    const body = (await request.json()) as { enabled?: boolean; config?: Record<string, unknown>; secret_ref?: string };
    let found = integrations.find((i) => i.kind === kind);
    if (!found) { found = { id: localId("int"), kind: kind as "JIRA" | "SLACK", enabled: false, config: {}, secret_ref: "" }; integrations.push(found); }
    found.enabled = body.enabled ?? found.enabled;
    found.config = body.config ?? found.config;
    found.secret_ref = body.secret_ref ?? found.secret_ref;
    return HttpResponse.json(found);
  }),

  // ---- AI ------------------------------------------------------------------
  http.post(`${API}/ai/chat`, async ({ request }) => {
    await delay(ACTION_DELAY + 350);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (!store.featureFlags.chat) return forbidden("Chat is not in your plan.");
    const body = (await request.json()) as { query?: string };
    const query = (body.query ?? "").trim();
    if (!query) return HttpResponse.json({ detail: "Query is required." }, { status: 400 });
    const lower = query.toLowerCase();
    if (/(approve|reject|create|update|delete|change|set |publish|finalize)/.test(lower)) {
      return HttpResponse.json({ status: "blocked", intent: "write", answer: "I'm a read-only assistant — I can't make changes or approvals." });
    }
    return HttpResponse.json({
      status: "ok", intent: "read",
      answer: `Based on your access, here's what I found for "${query}". (Demo answer — the chat agent is RBAC-scoped and read-only.)`,
      data: ["Ship platform v2", "Mentor 2 engineers", "Cut p95 latency"],
    });
  }),
  http.get(`${API}/ai/nudges`, async ({ request }) => {
    await delay(GET_DELAY);
    const u = currentUser(request);
    if (!u) return unauthorized();
    if (u.role === "EMPLOYEE") return forbidden();
    return HttpResponse.json(nudgesFor(u.role));
  }),
];

// ---- transition helpers ----------------------------------------------------

type CriticalRoleRisk = "LOW" | "MEDIUM" | "HIGH";
type BenchReadiness = "READY_NOW" | "READY_SOON" | "DEVELOPING" | "NOT_READY";
type BenchBand = "LOW" | "MEDIUM" | "HIGH";

function reviewTransition(
  action: string,
  apply: (r: (typeof reviews)[number], body: Record<string, string> | undefined, u: AdminUser) => Response | null,
) {
  return [
    http.post(`${API}/reviews/:id/${action}`, async ({ request, params }) => {
      await delay(ACTION_DELAY);
      const u = currentUser(request);
      if (!u) return unauthorized();
      if (!atLeast(u.role, "MANAGER")) return forbidden();
      const r = reviews.find((x) => x.id === params.id);
      if (!r) return notFound();
      const body = (await request.json().catch(() => ({}))) as Record<string, string>;
      const result = apply(r, body, u);
      return result ?? HttpResponse.json(r);
    }),
  ];
}

function jdTransition(
  action: string,
  apply: (jd: (typeof jds)[number], body: Record<string, unknown> | undefined) => Response | null,
) {
  return [
    http.post(`${API}/jd/:id/${action}`, async ({ request, params }) => {
      await delay(ACTION_DELAY);
      const u = currentUser(request);
      if (!u) return unauthorized();
      if (!atLeast(u.role, "HRBP")) return forbidden();
      const jd = jds.find((x) => x.id === params.id);
      if (!jd) return notFound();
      const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
      if (action === "save-draft" && body && "body" in body && body.body) {
        const versions = jdVersions[jd.id] ?? [];
        if (versions[0]) versions[0].body = body.body as (typeof versions)[number]["body"];
      }
      const result = apply(jd, body);
      return result ?? HttpResponse.json(jd);
    }),
  ];
}
