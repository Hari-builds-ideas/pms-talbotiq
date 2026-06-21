/**
 * Color-contrast guard (WCAG 1.4.3, AA). jsdom has no layout engine, so axe can't
 * compute contrast — this reads the ACTUAL design tokens from globals.css and
 * checks the real foreground/background pairs the UI renders (notably the Badge
 * `text-<tone>` on `bg-<tone>-subtle` pattern, which is small text → needs 4.5:1).
 * If a token is retuned and drops below AA, this fails.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// vitest runs from the frontend/ project root.
const css = readFileSync(resolve(process.cwd(), "src/styles/globals.css"), "utf8");

/** Pull `--name: H S% L%;` HSL triples from the :root block. */
function token(name: string): [number, number, number] {
  const m = css.match(new RegExp(`--${name}:\\s*([\\d.]+)\\s+([\\d.]+)%\\s+([\\d.]+)%`));
  if (!m) throw new Error(`token --${name} not found`);
  return [Number(m[1]), Number(m[2]), Number(m[3])];
}

function hslToRgb([h, s, l]: [number, number, number]) {
  s /= 100;
  l /= 100;
  const k = (n: number) => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = (n: number) => l - a * Math.max(-1, Math.min(k(n) - 3, 9 - k(n), 1));
  return [f(0), f(8), f(4)];
}

function luminance([h, s, l]: [number, number, number]) {
  const lin = hslToRgb([h, s, l]).map((v) =>
    v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4),
  );
  return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
}

function contrast(fg: [number, number, number], bg: [number, number, number]) {
  const a = luminance(fg);
  const b = luminance(bg);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

// Pairs that render as NORMAL-size text → require 4.5:1.
const TEXT_PAIRS: Array<[string, [number, number, number], [number, number, number]]> = [
  ["body text (foreground/background)", token("foreground"), token("background")],
  ["secondary text (muted-foreground/background)", token("muted-foreground"), token("background")],
  ["secondary text (muted-foreground/card)", token("muted-foreground"), token("card")],
  ["secondary-foreground/secondary", token("secondary-foreground"), token("secondary")],
  ["primary label (primary-foreground/primary)", token("primary-foreground"), token("primary")],
  ["badge default (primary/background)", token("primary"), token("background")],
  ["badge success (success/success-subtle)", token("success"), token("success-subtle")],
  ["badge warning (warning/warning-subtle)", token("warning"), token("warning-subtle")],
  ["badge danger (danger/danger-subtle)", token("danger"), token("danger-subtle")],
  ["badge info (info/info-subtle)", token("info"), token("info-subtle")],
  ["badge ai (ai/ai-subtle)", token("ai"), token("ai-subtle")],
  ["badge premium (premium/premium-subtle)", token("premium"), token("premium-subtle")],
  ["sidebar nav (sidebar-foreground/sidebar)", token("sidebar-foreground"), token("sidebar")],
  ["sidebar muted (sidebar-muted/sidebar)", token("sidebar-muted"), token("sidebar")],
];

describe("WCAG 1.4.3 — token contrast (normal text ≥ 4.5:1)", () => {
  for (const [name, fg, bg] of TEXT_PAIRS) {
    it(name, () => {
      const ratio = contrast(fg, bg);
      expect(ratio, `${name}: ${ratio.toFixed(2)}:1 (need ≥ 4.5)`).toBeGreaterThanOrEqual(4.5);
    });
  }
});
