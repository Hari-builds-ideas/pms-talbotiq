import { Outlet, useLocation } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ChatProvider } from "@/features/chat/ChatPanel";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { CommandPalette } from "@/features/command/CommandPalette";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

/** The authenticated app shell: dark sidebar + topbar + scrollable content.
 * A render error in any screen is caught by the boundary (the shell stays
 * usable); navigating to a new route clears it. */
export function AppLayout() {
  const location = useLocation();
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
          <Sidebar />
          <div className="flex min-w-0 flex-1 flex-col">
            <Topbar />
            <main
              id="main-content"
              tabIndex={-1}
              className="flex-1 overflow-y-auto scrollbar-thin focus:outline-none"
            >
              <div className="mx-auto w-full max-w-[1400px] px-6 py-6">
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
