import { Bell, LogOut, Menu, Search, Sparkles, UserCog } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAuth } from "@/lib/auth/AuthContext";
import { useChatPanel } from "@/features/chat/ChatPanel";
import { approvalsApi, feedbackApi } from "@/lib/api/endpoints";
import { ROLE_LABEL, ROLE_RANK, type Role } from "@/lib/enums";
import { initials } from "@/lib/format";

const USING_MOCKS = import.meta.env.VITE_USE_MOCKS === "true";

/** Dev-only identities for previewing each role (mock layer). */
const DEV_IDENTITIES: Array<{ id: string; label: string }> = [
  { id: "u-admin-001", label: "Admin" },
  { id: "u-hrbp", label: "HRBP" },
  { id: "u-1", label: "Manager" },
];

/** Real pending-actions count (N5): feedback requests for everyone + the approval
 *  inbox for managers+. Same query keys as the dashboard cockpits, so it shares the
 *  react-query cache (no extra network). */
function usePendingCount(): { total: number; approvals: number } {
  const { me } = useAuth();
  const isManagerPlus = me ? ROLE_RANK[me.role as Role] >= ROLE_RANK["MANAGER"] : false;
  const requests = useQuery({
    queryKey: ["feedback", "requests", "mine"],
    queryFn: feedbackApi.requestsMine,
  });
  const inbox = useQuery({
    queryKey: ["approvals", "inbox"],
    queryFn: approvalsApi.inbox,
    enabled: isManagerPlus,
  });
  const pendingRequests = (requests.data ?? []).filter((r) => r.status === "PENDING").length;
  const pendingApprovals = inbox.data?.length ?? 0;
  // Return the breakdown so the bell can open the queue that actually HAS the items —
  // an HRBP with 1 feedback request + 0 approvals was sent to an empty /approvals
  // (phantom "1"). BUGS_FOUND #12.
  return { total: pendingRequests + pendingApprovals, approvals: pendingApprovals };
}

function openCommandPalette() {
  document.dispatchEvent(
    new KeyboardEvent("keydown", { key: "k", metaKey: true, ctrlKey: true }),
  );
}

export function Topbar({ onToggleNav }: { onToggleNav?: () => void }) {
  const { me, logout, completeLogin } = useAuth();
  const chat = useChatPanel();
  const navigate = useNavigate();
  const { total: pending, approvals } = usePendingCount();

  function switchTo(id: string) {
    void completeLogin({ access: `mock.${id}`, refresh: `mockr.${id}` });
  }

  return (
    // pt-safe clears the notch; px-safe clears the landscape rounded corners.
    // min-w-0 on the header itself so it can never be widened by its children.
    <header className="flex h-16 min-w-0 shrink-0 items-center gap-2 border-b border-border bg-card px-3 pt-safe px-safe sm:gap-3 sm:px-5">
      {/* Left: collapse toggle. h-11 w-11 = a 44x44 tap target; it was 16x32,
          and on a phone this is the ONLY way to open navigation. */}
      <Button
        variant="ghost"
        size="icon-sm"
        onClick={onToggleNav}
        aria-label="Toggle navigation"
        className="h-11 w-11 shrink-0 text-muted-foreground"
      >
        <Menu className="h-5 w-5" />
      </Button>

      {/* Center: global search.
          min-w-0 is load-bearing. A flex child defaults to min-width:auto, which
          refuses to shrink below its content — so this button held its full
          ~299px and pushed the entire right-hand cluster (notifications, Ask AI,
          and the account menu, which is the only route to Sign out) to right:487
          on a 390px screen. Off the edge, unreachable, on every route for every
          role. See docs/BUILD/MOBILE_AUDIT.md finding 2.
          Below sm the label and the ⌘K hint are dropped: a phone has no ⌘ key and
          no room for the sentence, so it collapses to a 44px icon button. */}
      <button
        type="button"
        onClick={openCommandPalette}
        aria-label="Search"
        className="flex h-11 w-11 min-w-0 shrink items-center justify-center gap-2.5 rounded-xl border border-input bg-input-background text-sm text-muted-foreground transition-colors hover:bg-secondary sm:h-10 sm:w-auto sm:max-w-xl sm:flex-1 sm:justify-start sm:px-3.5"
      >
        <Search className="h-4 w-4 shrink-0" />
        <span className="hidden truncate sm:inline">Search employees, OKRs, goals…</span>
        <kbd className="ml-auto hidden rounded border border-border bg-card px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground sm:inline">
          ⌘K
        </kbd>
      </button>

      {/* Right: dev switcher · notifications · help/AI · identity.
          shrink-0 + ml-auto so this cluster keeps its width and stays pinned to
          the right edge rather than being pushed past it. */}
      <div className="ml-auto flex shrink-0 items-center gap-0.5 sm:gap-1.5">
        {USING_MOCKS && (
          <DropdownMenu>
            <Tooltip>
              <TooltipTrigger asChild>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" className="gap-1.5" aria-label="Preview role (dev)">
                    <UserCog className="h-4 w-4" />
                    <span className="hidden md:inline">Preview role</span>
                  </Button>
                </DropdownMenuTrigger>
              </TooltipTrigger>
              <TooltipContent>Dev: switch role (mock data)</TooltipContent>
            </Tooltip>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>Preview as</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {DEV_IDENTITIES.map((d) => (
                <DropdownMenuItem key={d.id} onClick={() => switchTo(d.id)}>
                  {d.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        )}

        {/* Notifications — real pending-actions count; opens the relevant queue. */}
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={() => navigate(approvals > 0 ? "/approvals" : "/feedback")}
              aria-label={`Pending actions: ${pending}`}
              className="relative flex h-11 w-11 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            >
              <Bell className="h-[18px] w-[18px]" />
              {pending > 0 && (
                <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-semibold text-danger-foreground">
                  {pending > 9 ? "9+" : pending}
                </span>
              )}
            </button>
          </TooltipTrigger>
          <TooltipContent>{pending > 0 ? `${pending} pending action${pending === 1 ? "" : "s"}` : "No pending actions"}</TooltipContent>
        </Tooltip>

        {/* Ask AI — first-class agent entry point (AGENT_UX_V3 Part 2.1) */}
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={chat.toggle}
              aria-label="Ask AI"
              className="flex h-11 w-11 items-center justify-center rounded-lg text-ai transition-colors hover:bg-ai-subtle"
            >
              <Sparkles className="h-[18px] w-[18px]" />
            </button>
          </TooltipTrigger>
          <TooltipContent>Ask AI — plan &amp; approve multi-step work</TooltipContent>
        </Tooltip>

        {/* (Removed the duplicate "?" help button — it opened the same chat as Ask AI.
            BUGS_FOUND #10. A real help/docs affordance can be added later.) */}

        <div className="mx-1 hidden h-6 w-px bg-border sm:block" />

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button aria-label="Open account menu" className="flex h-11 min-w-11 items-center gap-2.5 rounded-lg px-1.5 py-1 transition-colors hover:bg-secondary">
              <Avatar>
                <AvatarFallback>{initials(me?.display)}</AvatarFallback>
              </Avatar>
              <div className="hidden text-left leading-tight sm:block">
                <div className="max-w-[12rem] truncate text-sm font-semibold text-foreground">
                  {me?.display ?? "—"}
                </div>
                <div className="text-2xs text-muted-foreground">
                  {me ? ROLE_LABEL[me.role as Role] : ""}
                </div>
              </div>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>
              <div className="space-y-0.5">
                <div className="truncate font-medium text-foreground">
                  {me?.display}
                </div>
                <div className="truncate text-2xs font-normal text-muted-foreground">
                  {me?.email}
                </div>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => navigate("/settings")}>
              <UserCog className="h-4 w-4" />
              My settings
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => void logout()}>
              <LogOut className="h-4 w-4" />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
