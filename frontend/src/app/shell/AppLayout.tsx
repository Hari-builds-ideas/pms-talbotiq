import { Outlet } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ChatProvider } from "@/features/chat/ChatPanel";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

/** The authenticated app shell: dark sidebar + topbar + scrollable content. */
export function AppLayout() {
  return (
    <TooltipProvider delayDuration={200}>
      <ChatProvider>
        <div className="flex h-screen overflow-hidden bg-background">
          <Sidebar />
          <div className="flex min-w-0 flex-1 flex-col">
            <Topbar />
            <main className="flex-1 overflow-y-auto scrollbar-thin">
              <div className="mx-auto w-full max-w-[1400px] px-6 py-6">
                <Outlet />
              </div>
            </main>
          </div>
        </div>
      </ChatProvider>
    </TooltipProvider>
  );
}
