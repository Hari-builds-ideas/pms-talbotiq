/**
 * Time-of-day greeting, resolved in the USER's timezone.
 *
 * The old implementation read `new Date().getHours()`, which is the *device's*
 * clock. A phone or a container set to UTC while the person is in IST is 5.5
 * hours out, so the dashboard said "Good evening" at midnight — the reported bug.
 *
 * Resolution order (A4): the tenant user's own `timezone` field → the browser's
 * resolved IANA zone → the device clock. Each step is a real fallback, not a
 * guess: an unset profile timezone is common, and `resolvedOptions()` is absent
 * on very old engines.
 */

export type GreetingBand = "morning" | "afternoon" | "evening" | "night";

/** Band boundaries, local to the resolved timezone.
 *  05:00–11:59 morning · 12:00–16:59 afternoon · 17:00–20:59 evening ·
 *  21:00–04:59 night. */
export function bandForHour(hour: number): GreetingBand {
  if (hour >= 5 && hour < 12) return "morning";
  if (hour >= 12 && hour < 17) return "afternoon";
  if (hour >= 17 && hour < 21) return "evening";
  return "night";
}

const LABEL: Record<GreetingBand, string> = {
  morning: "Good morning",
  afternoon: "Good afternoon",
  evening: "Good evening",
  night: "Good night",
};

/**
 * The hour (0-23) that `at` represents in `timeZone`.
 *
 * Uses Intl rather than arithmetic on the UTC offset so DST is handled by the
 * platform's tz database. An invalid or unknown zone throws inside Intl; we
 * fall back to the device clock rather than letting the dashboard fail to render
 * over a bad profile value.
 */
export function hourIn(timeZone: string | undefined, at: Date = new Date()): number {
  if (timeZone) {
    try {
      const hour = new Intl.DateTimeFormat("en-GB", {
        hour: "numeric",
        hour12: false,
        timeZone,
      }).format(at);
      const parsed = Number(hour);
      // "24" is what some engines emit for midnight under hour12:false.
      if (Number.isFinite(parsed)) return parsed % 24;
    } catch {
      /* unknown zone — fall through to the device clock */
    }
  }
  return at.getHours();
}

/** The browser's own IANA zone, when it can tell us. */
export function browserTimeZone(): string | undefined {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || undefined;
  } catch {
    return undefined;
  }
}

/**
 * "Good morning" / "Good afternoon" / "Good evening" / "Good night" for the
 * given user timezone. `at` is injectable so the bands can be tested against a
 * pinned clock instead of whenever CI happens to run.
 */
export function greetingFor(
  timeZone?: string,
  at: Date = new Date(),
): string {
  return LABEL[bandForHour(hourIn(timeZone ?? browserTimeZone(), at))];
}
