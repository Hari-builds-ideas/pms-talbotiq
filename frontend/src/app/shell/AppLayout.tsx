import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useAuth } from "@/lib/auth/AuthContext";
import { ChatProvider, useChatPanel } from "@/features/chat/ChatPanel";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { CommandPalette } from "@/features/command/CommandPalette";
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
          className="sr-only z-50 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground focus:not-sr-only focus:absolute focus:left-4 focus:top-4"
        >
          Skip to main content
        </a>
        <CommandPalette />
        <ShellFrame />
      </ChatProvider>
    </TooltipProvider>
  );
}

/** Is the viewport at Tailwind's `lg` breakpoint or wider?
 *
 * Guarded rather than calling `window.matchMedia` directly: it does not exist under
 * SSR, and jsdom does not implement it either, so an unguarded call takes out every
 * test that renders the shell. Absent → assume desktop, which is the layout this app
 * has always had. */
function isDesktopViewport(): boolean {
  return (
    typeof window === "undefined" ||
    typeof window.matchMedia !== "function" ||
    window.matchMedia("(min-width: 1024px)").matches
  );
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
  // Open on desktop, CLOSED on a phone. It used to start open at every width, and
  // since the sidebar is 256px wide that left a 390px screen about 130px of content:
  // the dashboard rendered with its stat cards overlapping each other. The topbar's
  // menu button already toggled it — only the default was wrong.
  const [navOpen, setNavOpen] = useState(isDesktopViewport);
  // Close it again after navigating on mobile, where it sits ON TOP of the page —
  // otherwise tapping a nav item leaves the menu covering the screen you asked for.
  useEffect(() => {
    if (!isDesktopViewport()) setNavOpen(false);
  }, [location.pathname]);
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
        "flex h-screen overflow-hidden bg-background",
        chatOpen && "sm:mr-[var(--chat-w)]",
      )}
      style={{ "--chat-w": `${chatWidth}px` } as React.CSSProperties}
    >
      {navOpen && <Sidebar />}
      {/* Backdrop for the overlaying mobile sidebar: gives it an obvious way to be
          dismissed. lg:hidden so the desktop layout is untouched. */}
      {navOpen && (
        <button
          type="button"
          aria-label="Close navigation"
          onClick={() => setNavOpen(false)}
          className="fixed inset-0 z-30 bg-black/40 lg:hidden"
        />
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onToggleNav={() => setNavOpen((v) => !v)} />
        <main
          id="main-content"
          tabIndex={-1}
          className="flex-1 overflow-y-auto scrollbar-thin focus:outline-none"
        >
          <div className="mx-auto w-full max-w-[1440px] px-6 py-8">
            <ErrorBoundary resetKey={location.pathname}>
              <Outlet />
            </ErrorBoundary>
          </div>
        </main>
      </div>
    </div>
  );
}
