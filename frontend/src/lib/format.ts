import { format, formatDistanceToNowStrict, isValid, parseISO } from "date-fns";

/**
 * Formatting helpers. Per open-question #2: datetimes are UTC ISO-8601 and shown
 * in browser-local time; plain dates render as-is. Decimals are strings (2dp).
 */

/** A datetime → local "13 Jun 2026, 14:05". */
export function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const d = parseISO(value);
  if (!isValid(d)) return value;
  return format(d, "d MMM yyyy, HH:mm");
}

/** A plain date (or datetime) → "13 Jun 2026". */
export function formatDate(value?: string | null): string {
  if (!value) return "—";
  const d = parseISO(value);
  if (!isValid(d)) return value;
  return format(d, "d MMM yyyy");
}

/** Relative time, e.g. "in 3 days" / "2 hours ago". */
export function formatRelative(value?: string | null): string {
  if (!value) return "—";
  const d = parseISO(value);
  if (!isValid(d)) return value;
  const distance = formatDistanceToNowStrict(d, { addSuffix: true });
  return distance;
}

/** True when an ISO datetime is in the past (for overdue indicators). */
export function isOverdue(value?: string | null): boolean {
  if (!value) return false;
  const d = parseISO(value);
  return isValid(d) && d.getTime() < Date.now();
}

/** Render a decimal STRING at a fixed precision without float drift. */
export function formatDecimal(value?: string | number | null, dp = 2): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) return String(value);
  return n.toFixed(dp);
}

/** A 0–1 confidence score → "82%". */
export function formatConfidence(value?: string | number | null): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) return "—";
  return `${Math.round(n * 100)}%`;
}

/** T-score (string or number) → one-dp display. */
export function formatScore(value?: string | number | null): string {
  return formatDecimal(value, 1);
}

/** Truncate a long id for compact display (keeps the suffix). */
export function shortId(id?: string | null): string {
  if (!id) return "—";
  return id.length > 12 ? `…${id.slice(-8)}` : id;
}

/** Initials from a display name or email, for avatars. */
export function initials(nameOrEmail?: string | null): string {
  if (!nameOrEmail) return "?";
  const base = nameOrEmail.includes("@")
    ? nameOrEmail.split("@")[0]
    : nameOrEmail;
  const parts = base.split(/[\s._-]+/).filter(Boolean);
  if (parts.length === 0) return base.slice(0, 2).toUpperCase();
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
