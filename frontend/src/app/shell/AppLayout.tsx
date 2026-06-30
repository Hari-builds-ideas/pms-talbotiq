import { useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ChatProvider } from "@/features/chat/ChatPanel";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { CommandPalette } from "@/features/command/CommandPalette";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

/** The authenticated app shell: light sidebar + topbar + scrollable content.
 * The topbar's menu button collapses the sidebar. A render error in any screen is
 * caught by the boundary (the shell stays usable); navigating clears it. */
export function AppLayout() {
  const location = useLocation();
  const [navOpen, setNavOpen] = useState(true);
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
        <div className="flex h-screen overflow-hidden bg-background">
          {navOpen && <Sidebar />}
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
      </ChatProvider>
    </TooltipProvider>
  );
}
