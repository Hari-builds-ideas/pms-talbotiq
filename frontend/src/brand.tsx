import { useState } from "react";
import { Sprout } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * ── SINGLE SOURCE OF TRUTH FOR PRODUCT BRANDING ─────────────────────────────
 *
 * The entire rebrand — product NAME and every LOGO/FAVICON reference in the
 * app UI — is routed through this one module. Nothing user-facing hardcodes
 * "Axiom" or an asset path; it all comes from here.
 *
 * TO REVERT to the legacy "Talbotiq PMS" identity: set `REBRAND = false` below.
 * That single flag swaps the name AND every logo back to the old lockup
 * (the inline green "leaf" mark). Nothing else needs to change.
 *
 * TO CHANGE ONLY THE DISPLAY NAME without touching code: set `VITE_APP_NAME`
 * in the build environment — it overrides the name (assets stay as configured).
 *
 * TO MAKE THE REBRAND PERMANENT (drop the legacy fallback): keep REBRAND=true;
 * it already is the shipped default. The LEGACY block can be deleted later if
 * you never want to switch back.
 *
 * The favicon/tab-title live in `frontend/index.html` (static, pre-React) and
 * are documented alongside this file in docs/PROD_READY_REPORT.md.
 * ---------------------------------------------------------------------------
 */

/** ⇦ THE ONE SWITCH. false = legacy "Talbotiq PMS" leaf branding. */
const REBRAND = true;

type BrandConfig = {
  /** Full product name — browser tab, login, emails, prose. */
  name: string;
  /** Short lockup label shown next to the mark in the sidebar header. */
  shortName: string;
  /** One-line product tagline for the login brand panel. */
  tagline: string;
  /** Icon mark tuned for LIGHT backgrounds (green). */
  iconOnLight: string;
  /** Icon mark tuned for DARK backgrounds (white). */
  iconOnDark: string;
  /** Horizontal wordmark for LIGHT backgrounds (green). */
  wordmarkOnLight: string;
  /** Horizontal wordmark for DARK backgrounds (white). */
  wordmarkOnDark: string;
};

const AXIOM: BrandConfig = {
  name: "Axiom",
  shortName: "Axiom",
  tagline: "Talent intelligence & performance management for modern teams.",
  // The real brand PNGs live in frontend/public/favicon/. The source icon-*.png
  // has heavy transparent padding (the mark fills only ~50%×64%), so it renders
  // as a tiny speck at small sizes — we use tightly-cropped derivatives
  // (/brand/mark-*.png, cropped to the mark's alpha bbox) so it fills its box and
  // reads as a real logo. Green on light surfaces, white on dark. The horizontal
  // wordmark (logo-*, already edge-to-edge) is the full lockup for the login panel.
  iconOnLight: "/brand/mark-green.png",
  iconOnDark: "/brand/mark-white.png",
  wordmarkOnLight: "/favicon/logo-green.png",
  wordmarkOnDark: "/favicon/logo-white.png",
};

const LEGACY: BrandConfig = {
  name: "Talbotiq PMS",
  shortName: "TalbotIQ",
  tagline: "Talent intelligence & performance management for modern teams.",
  // Legacy used an inline lucide leaf, not image assets — these paths are only
  // referenced when REBRAND is true, so they stay unused in legacy mode.
  iconOnLight: "/favicon.svg",
  iconOnDark: "/favicon.svg",
  wordmarkOnLight: "/favicon.svg",
  wordmarkOnDark: "/favicon.svg",
};

const active = REBRAND ? AXIOM : LEGACY;
const envName =
  (import.meta.env.VITE_APP_NAME as string | undefined)?.trim() || "";

/** The resolved brand — import this everywhere the name/assets are needed. */
export const BRAND: BrandConfig = {
  ...active,
  name: envName || active.name,
  shortName: envName || active.shortName,
};

/** True when the image-based rebrand is active (vs the legacy inline mark). */
export const IS_REBRANDED = REBRAND;

/**
 * Brand icon mark. Renders the image asset when rebranded, or the legacy
 * lucide leaf otherwise — so a single component keeps the swap reversible.
 * `onDark` picks the white variant for dark surfaces.
 */
export function BrandMark({
  onDark = false,
  className,
}: {
  onDark?: boolean;
  className?: string;
}) {
  // A PNG that 404s renders as nothing (or a browser's broken-image glyph), which
  // is how "the logo just isn't there" reports happen — a wrong base path, a
  // missing file in public/, or a CDN rewrite is enough. Fall back to the inline
  // vector mark so the brand slot is never empty. See A5.
  const [broken, setBroken] = useState(false);
  if (!REBRAND || broken) return <Sprout className={className} aria-hidden />;
  return (
    <img
      src={onDark ? BRAND.iconOnDark : BRAND.iconOnLight}
      alt=""
      aria-hidden
      onError={() => setBroken(true)}
      className={cn("object-contain", className)}
    />
  );
}

/**
 * Horizontal wordmark (icon + name lockup as one image when rebranded).
 * Falls back to the legacy leaf + text lockup in legacy mode.
 */
export function BrandWordmark({
  onDark = false,
  className,
}: {
  onDark?: boolean;
  className?: string;
}) {
  // Same fallback as BrandMark: a missing wordmark degrades to the mark + name
  // lockup rather than an empty box with alt text floating in it.
  const [broken, setBroken] = useState(false);
  if (!REBRAND || broken) {
    return (
      <span className="flex items-center gap-2.5">
        <Sprout className="h-5 w-5" aria-hidden />
        <span className="text-lg font-semibold">{BRAND.name}</span>
      </span>
    );
  }
  return (
    <img
      src={onDark ? BRAND.wordmarkOnDark : BRAND.wordmarkOnLight}
      alt={BRAND.name}
      onError={() => setBroken(true)}
      className={cn("object-contain", className)}
    />
  );
}
