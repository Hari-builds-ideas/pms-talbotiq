/**
 * Greeting bands, against a PINNED clock.
 *
 * The bug this guards: the greeting read the device clock, so a browser or
 * container in UTC greeted a user in IST with "Good evening" at midnight. Every
 * case below therefore fixes both the instant and the zone.
 */
import { describe, expect, it } from "vitest";
import { bandForHour, greetingFor, hourIn } from "./greeting";

describe("bandForHour", () => {
  it("maps every hour of the day to exactly one band", () => {
    const bands = Array.from({ length: 24 }, (_, h) => bandForHour(h));
    expect(bands).toEqual([
      // 00-04 night
      "night", "night", "night", "night", "night",
      // 05-11 morning
      "morning", "morning", "morning", "morning", "morning", "morning", "morning",
      // 12-16 afternoon
      "afternoon", "afternoon", "afternoon", "afternoon", "afternoon",
      // 17-20 evening
      "evening", "evening", "evening", "evening",
      // 21-23 night
      "night", "night", "night",
    ]);
  });

  it("puts each boundary hour on the correct side", () => {
    expect(bandForHour(4)).toBe("night");
    expect(bandForHour(5)).toBe("morning");
    expect(bandForHour(11)).toBe("morning");
    expect(bandForHour(12)).toBe("afternoon");
    expect(bandForHour(16)).toBe("afternoon");
    expect(bandForHour(17)).toBe("evening");
    expect(bandForHour(20)).toBe("evening");
    expect(bandForHour(21)).toBe("night");
  });
});

describe("hourIn", () => {
  it("reads the hour in the requested zone, not the host's", () => {
    // 2026-08-17T18:35:00Z is 00:05 the next day in Kolkata (+05:30).
    const at = new Date("2026-08-17T18:35:00Z");
    expect(hourIn("UTC", at)).toBe(18);
    expect(hourIn("Asia/Kolkata", at)).toBe(0);
    expect(hourIn("America/New_York", at)).toBe(14);
  });

  it("returns 0 for midnight rather than 24", () => {
    // Some engines format midnight as "24" under hour12:false.
    expect(hourIn("Asia/Kolkata", new Date("2026-08-17T18:30:00Z"))).toBe(0);
    expect(hourIn("UTC", new Date("2026-08-17T00:00:00Z"))).toBe(0);
  });

  it("falls back to the device clock for an unknown zone instead of throwing", () => {
    const at = new Date("2026-08-17T12:00:00Z");
    expect(() => hourIn("Not/AZone", at)).not.toThrow();
    expect(hourIn("Not/AZone", at)).toBe(at.getHours());
  });

  it("honours DST via the platform tz database", () => {
    // London is UTC+1 in August, UTC+0 in January.
    expect(hourIn("Europe/London", new Date("2026-08-17T12:00:00Z"))).toBe(13);
    expect(hourIn("Europe/London", new Date("2026-01-17T12:00:00Z"))).toBe(12);
  });
});

describe("greetingFor", () => {
  it("says Good night at midnight in the user's zone — the reported bug", () => {
    // The exact failure: 18:35 UTC is midnight in Kolkata. Reading the device
    // clock gave "Good evening"; reading the user's zone gives the night band.
    const midnightIST = new Date("2026-08-17T18:35:00Z");
    expect(greetingFor("Asia/Kolkata", midnightIST)).toBe("Good night");
    // Same instant, a user actually in UTC, is genuinely in the evening.
    expect(greetingFor("UTC", midnightIST)).toBe("Good evening");
  });

  it("covers each band in a fixed zone", () => {
    const at = (hhmm: string) => new Date(`2026-08-17T${hhmm}:00Z`);
    expect(greetingFor("UTC", at("00:30"))).toBe("Good night");
    expect(greetingFor("UTC", at("04:59"))).toBe("Good night");
    expect(greetingFor("UTC", at("05:00"))).toBe("Good morning");
    expect(greetingFor("UTC", at("11:59"))).toBe("Good morning");
    expect(greetingFor("UTC", at("12:00"))).toBe("Good afternoon");
    expect(greetingFor("UTC", at("16:59"))).toBe("Good afternoon");
    expect(greetingFor("UTC", at("17:00"))).toBe("Good evening");
    expect(greetingFor("UTC", at("20:59"))).toBe("Good evening");
    expect(greetingFor("UTC", at("21:00"))).toBe("Good night");
    expect(greetingFor("UTC", at("23:59"))).toBe("Good night");
  });

  it("still returns a greeting when the profile has no timezone", () => {
    // Falls through to the browser zone; the assertion is that it does not throw
    // and returns one of the four labels.
    expect([
      "Good morning",
      "Good afternoon",
      "Good evening",
      "Good night",
    ]).toContain(greetingFor(undefined, new Date("2026-08-17T09:00:00Z")));
  });
});
