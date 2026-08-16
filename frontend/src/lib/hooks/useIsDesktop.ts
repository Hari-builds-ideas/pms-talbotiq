import * as React from "react";

/**
 * Tailwind's `md`. The single definition of "is this a phone?" for layout code.
 *
 * Keep in step with the `md:` variants in the shell and DataTable — when the JS
 * breakpoint and the CSS breakpoint drift apart you get a drawer that thinks it
 * is inline, or a card list rendered next to a table header.
 */
export const DESKTOP_QUERY = "(min-width: 768px)";

/**
 * Guarded rather than calling `window.matchMedia` directly: it does not exist
 * under SSR, and jsdom does not implement it either, so an unguarded call takes
 * out every test that renders the shell. Absent → assume desktop, which is the
 * layout this app has always had.
 */
export function isDesktopViewport(): boolean {
  return (
    typeof window === "undefined" ||
    typeof window.matchMedia !== "function" ||
    window.matchMedia(DESKTOP_QUERY).matches
  );
}

/**
 * Live viewport class. Subscribes to the media query so rotating a phone or
 * resizing a window re-lays-out, instead of keeping whatever was true at mount.
 */
export function useIsDesktop(): boolean {
  const [desktop, setDesktop] = React.useState(isDesktopViewport);
  React.useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const mql = window.matchMedia(DESKTOP_QUERY);
    const onChange = () => setDesktop(mql.matches);
    // addEventListener is the modern API; addListener is the Safari <14 fallback.
    if (typeof mql.addEventListener === "function") {
      mql.addEventListener("change", onChange);
      return () => mql.removeEventListener("change", onChange);
    }
    mql.addListener?.(onChange);
    return () => mql.removeListener?.(onChange);
  }, []);
  return desktop;
}
