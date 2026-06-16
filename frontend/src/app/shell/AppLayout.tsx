import { Outlet, useLocation } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ChatProvider } from "@/features/chat/ChatPanel";
import { ErrorBoundary } from "@/components/ErrorBoundary";
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
        <div className="flex h-screen overflow-hidden bg-background">
          <Sidebar />
          <div className="flex min-w-0 flex-1 flex-col">
            <Topbar />
            <main className="flex-1 overflow-y-auto scrollbar-thin">
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
