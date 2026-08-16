import { useCallback, useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useAuth } from "@/lib/auth/AuthContext";
import { ChatProvider, useChatPanel } from "@/features/chat/ChatPanel";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { CommandPalette } from "@/features/command/CommandPalette";
import { isDesktopViewport, useIsDesktop } from "@/lib/hooks/useIsDesktop";
import { cn } from "@/lib/utils";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

/** The authenticated app shell: light sidebar + topbar + scrollable content.
 * The topbar's menu button collapses the sidebar. A render error in any screen is
 * caught by the boundary (the shell stays usable); navigating clears it. */
export function AppLayout() {
  return (
    <TooltipProvider delayDuration={200}>
      <ChatProvider>
        {/* Skip-to-content: first focusable element; visible only when focused. */}
        <a
          href="#main-content"
          className="tap-target sr-only z-50 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground focus:not-sr-only focus:absolute focus:left-4 focus:top-4"
        >
          Skip to main content
        </a>
        <CommandPalette />
        {/* SHELL-level boundary. The inner boundary (around <Outlet/>) keeps a
            crashed SCREEN from taking the shell down; this one keeps a crashed
            SHELL — Topbar, Sidebar, the chat provider — from taking the whole
            app down. Without it a single throw in Topbar unmounts the React root
            and leaves an empty #root: a white screen with no way back. That was
            a real, reproducible outage, not a hypothetical (see
            docs/BUILD/MOBILE_AUDIT.md finding 1). */}
        <ErrorBoundary>
          <ShellFrame />
        </ErrorBoundary>
      </ChatProvider>
    </TooltipProvider>
  );
}

/** Remembers the DESKTOP sidebar preference only. A mobile session always starts
 *  closed (A2), so an open drawer is never restored onto a phone. */
const NAV_PREF_KEY = "pms.nav.desktopOpen";

/** The stored desktop preference, defaulting to open. Never consulted on mobile. */
function readDesktopPref(): boolean {
  try {
    return window.localStorage.getItem(NAV_PREF_KEY) !== "false";
  } catch {
    return true;
  }
}

/** hex "#RRGGBB" → the "H S% L%" triple the CSS tokens use. */
function hexToHslTriple(hex: string): string | null {
  const m = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!m) return null;
  const n = parseInt(m[1], 16);
  const r = ((n >> 16) & 255) / 255;
  const g = ((n >> 8) & 255) / 255;
  const b = (n & 255) / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  let h = 0;
  let s = 0;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
    else if (max === g) h = ((b - r) / d + 2) / 6;
    else h = ((r - g) / d + 4) / 6;
  }
  return `${Math.round(h * 360)} ${Math.round(s * 100)}% ${Math.round(l * 100)}%`;
}

/** The shell body. Reads the chat panel state so the content column shrinks by the
 * panel's width when it's open (≥sm) — page and copilot truly side by side (E2);
 * on mobile the panel overlays instead (it's full-width there anyway). Applies the
 * tenant's primary brand color when the plan includes custom_branding (L1.5). */
function ShellFrame() {
  const location = useLocation();
  const isDesktop = useIsDesktop();
  // Open on desktop (honouring the stored preference), CLOSED on a phone. It used
  // to start open at every width, and since the sidebar is 256px wide that left a
  // 390px screen about 130px of content: the dashboard rendered with its stat
  // cards overlapping each other.
  const [navOpen, setNavOpen] = useState(
    () => isDesktopViewport() && readDesktopPref(),
  );
  // Below md the sidebar is a DRAWER: fixed, over the content, with a backdrop.
  const isDrawer = !isDesktop;

  // Crossing the breakpoint (rotation, window resize) re-applies the rule for the
  // side you land on: desktop restores the stored preference, mobile always closes.
  // Without this, rotating a phone to landscape-tablet width left the drawer state
  // stuck and the layout half-applied.
  useEffect(() => {
    setNavOpen(isDesktop ? readDesktopPref() : false);
  }, [isDesktop]);

  // Close it again after navigating on mobile, where it sits ON TOP of the page —
  // otherwise tapping a nav item leaves the menu covering the screen you asked for.
  useEffect(() => {
    if (isDrawer) setNavOpen(false);
  }, [location.pathname, isDrawer]);

  // Toggling persists ONLY on desktop. A phone's open drawer is session state, not
  // a preference, and restoring it on the next visit would put the menu back over
  // the content on load.
  const toggleNav = useCallback(() => {
    setNavOpen((open) => {
      const next = !open;
      if (isDesktop) {
        try {
          window.localStorage.setItem(NAV_PREF_KEY, String(next));
        } catch {
          /* private mode / storage disabled — the toggle still works in-session */
        }
      }
      return next;
    });
  }, [isDesktop]);

  const closeNav = useCallback(() => setNavOpen(false), []);
  const { open: chatOpen, width: chatWidth } = useChatPanel();
  const { me } = useAuth();
  const brandColor = me?.tenant_branding?.primary_color;
  useEffect(() => {
    const triple = brandColor ? hexToHslTriple(brandColor) : null;
    if (triple) document.documentElement.style.setProperty("--primary", triple);
    return () => {
      document.documentElement.style.removeProperty("--primary");
    };
  }, [brandColor]);
  return (
    <div
      className={cn(
        // 100dvh, not 100vh: on mobile Safari/Chrome the URL bar collapses on
        // scroll and 100vh keeps reserving the taller height, so the page jumps
        // and the last ~60px sit under the browser chrome. dvh tracks the real
        // visible height. h-screen stays as the fallback for older engines.
        "flex h-screen h-[100dvh] overflow-hidden bg-background",
        chatOpen && "sm:mr-[var(--chat-w)]",
      )}
      style={{ "--chat-w": `${chatWidth}px` } as React.CSSProperties}
    >
      {navOpen && <Sidebar drawer={isDrawer} onClose={closeNav} />}
      {/* Backdrop for the overlaying mobile sidebar: gives it an obvious way to be
          dismissed. Rendered only in drawer mode so the desktop layout is untouched. */}
      {navOpen && isDrawer && (
        <button
          type="button"
          aria-label="Close navigation"
          onClick={closeNav}
          className="fixed inset-0 z-30 bg-black/40"
        />
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onToggleNav={toggleNav} navOpen={navOpen} />
        <main
          id="main-content"
          tabIndex={-1}
          className="flex-1 overflow-y-auto overflow-x-hidden scrollbar-thin focus:outline-none"
        >
          {/* px-4 on a phone (px-6 wasted 12% of a 390px screen), px-6 from sm.
              pb-safe-4 keeps the last row clear of the home indicator. */}
          <div className="mx-auto w-full max-w-[1440px] px-4 py-6 pb-safe-4 sm:px-6 sm:py-8">
            <ErrorBoundary resetKey={location.pathname}>
              <Outlet />
            </ErrorBoundary>
          </div>
        </main>
      </div>
    </div>
  );
}
