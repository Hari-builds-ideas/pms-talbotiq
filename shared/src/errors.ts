import { AxiosError } from "axios";

/**
 * One shared error model + mapper (00_overview.md → HTTP status table).
 * Every screen reads `mapApiError` to render the right state and message.
 */

export type ApiErrorKind =
  | "bad_input" // 400
  | "unauthenticated" // 401
  | "forbidden" // 403
  | "not_found" // 404 — "not yours / not there"
  | "conflict" // 409 — illegal state transition
  | "domain" // 422 — { detail, code }
  | "rate_limited" // 429 — Retry-After / upgrade_hint
  | "ai_unavailable" // 503 — AI seam not configured
  | "network" // no response
  | "unknown";

export interface ApiError {
  kind: ApiErrorKind;
  status?: number;
  /** Human-readable message to surface. */
  message: string;
  /** Domain code on 422 (e.g. REPORTING_CYCLE, HITL_APPROVAL_REQUIRED). */
  code?: string;
  /** Field-level errors on a 400 (best-effort extraction). */
  fields?: Record<string, string[]>;
  /** Seconds to wait before retrying (429). */
  retryAfter?: number;
  /** Whether the 429 body carried an upgrade hint. */
  upgradeHint?: boolean;
  /** Raw response body for debugging. */
  raw?: unknown;
}

const DEFAULT_MESSAGES: Record<ApiErrorKind, string> = {
  bad_input: "Some details need fixing.",
  unauthenticated: "Your session expired. Please sign in again.",
  forbidden: "You don't have permission to do this.",
  not_found: "Not found, or not in your scope.",
  conflict: "This changed since you loaded it — refresh and try again.",
  domain: "That action isn't allowed right now.",
  rate_limited: "You've hit a usage limit. Try again shortly.",
  ai_unavailable: "AI isn't available yet — the manual path still works.",
  network: "Couldn't reach the server. Check your connection.",
  unknown: "Something went wrong.",
};

function statusToKind(status?: number): ApiErrorKind {
  switch (status) {
    case 400:
      return "bad_input";
    case 401:
      return "unauthenticated";
    case 403:
      return "forbidden";
    case 404:
      return "not_found";
    case 409:
      return "conflict";
    case 422:
      return "domain";
    case 429:
      return "rate_limited";
    case 503:
      return "ai_unavailable";
    default:
      return "unknown";
  }
}

function extractFieldErrors(
  body: unknown,
): Record<string, string[]> | undefined {
  if (!body || typeof body !== "object") return undefined;
  const out: Record<string, string[]> = {};
  for (const [key, val] of Object.entries(body as Record<string, unknown>)) {
    if (key === "detail" || key === "code") continue;
    if (Array.isArray(val) && val.every((v) => typeof v === "string")) {
      out[key] = val as string[];
    } else if (typeof val === "string") {
      out[key] = [val];
    }
  }
  return Object.keys(out).length ? out : undefined;
}

export function mapApiError(err: unknown): ApiError {
  // Already mapped
  if (isApiError(err)) return err;

  if (err instanceof AxiosError) {
    const status = err.response?.status;
    const kind = statusToKind(status);
    const body = err.response?.data as
      | { detail?: string; code?: string; upgrade_hint?: unknown }
      | undefined;

    if (!err.response) {
      return { kind: "network", message: DEFAULT_MESSAGES.network, raw: err.message };
    }

    const retryAfterHeader = err.response.headers?.["retry-after"];
    const retryAfter = retryAfterHeader ? Number(retryAfterHeader) : undefined;

    const message =
      (body && typeof body.detail === "string" && body.detail) ||
      DEFAULT_MESSAGES[kind];

    return {
      kind,
      status,
      message,
      code: body?.code,
      fields: kind === "bad_input" ? extractFieldErrors(body) : undefined,
      retryAfter: Number.isFinite(retryAfter) ? retryAfter : undefined,
      upgradeHint: Boolean(body?.upgrade_hint),
      raw: body,
    };
  }

  if (err instanceof Error) {
    return { kind: "unknown", message: err.message || DEFAULT_MESSAGES.unknown };
  }

  return { kind: "unknown", message: DEFAULT_MESSAGES.unknown, raw: err };
}

export function isApiError(value: unknown): value is ApiError {
  return (
    typeof value === "object" &&
    value !== null &&
    "kind" in value &&
    "message" in value
  );
}

/** Short toast title per error kind. */
export function errorTitle(kind: ApiErrorKind): string {
  switch (kind) {
    case "forbidden":
      return "Not permitted";
    case "not_found":
      return "Not found";
    case "conflict":
      return "Out of date";
    case "domain":
      return "Can't do that yet";
    case "rate_limited":
      return "Slow down";
    case "ai_unavailable":
      return "AI unavailable";
    case "network":
      return "Connection problem";
    case "bad_input":
      return "Check your input";
    default:
      return "Error";
  }
}
