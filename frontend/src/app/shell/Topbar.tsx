import { LogOut, Sparkles, UserCog } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
import { ROLE_LABEL, type Role } from "@/lib/enums";
import { initials } from "@/lib/format";

const USING_MOCKS = import.meta.env.VITE_USE_MOCKS === "true";

/** Dev-only identities for previewing each role (mock layer). */
const DEV_IDENTITIES: Array<{ id: string; label: string }> = [
  { id: "u-admin-001", label: "Admin" },
  { id: "u-hrbp", label: "HRBP" },
  { id: "u-1", label: "Manager" },
];

export function Topbar() {
  const { me, logout, completeLogin } = useAuth();
  const chat = useChatPanel();

  function switchTo(id: string) {
    void completeLogin({ access: `mock.${id}`, refresh: `mockr.${id}` });
  }

  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-border bg-card/80 px-5 backdrop-blur">
      <div className="flex items-center gap-2 text-sm">
        <span className="font-medium text-foreground">{me?.tenant_name ?? "—"}</span>
        <Badge variant="muted" className="hidden sm:inline-flex">
          Tenant
        </Badge>
      </div>

      <div className="flex items-center gap-2">
        {USING_MOCKS && (
          <DropdownMenu>
            <Tooltip>
              <TooltipTrigger asChild>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" className="gap-1.5">
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

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={chat.toggle}
            >
              <Sparkles className="h-4 w-4 text-ai" />
              <span className="hidden md:inline">Ask AI</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent>Open the AI assistant</TooltipContent>
        </Tooltip>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="flex items-center gap-2 rounded-md px-1.5 py-1 transition-colors hover:bg-secondary">
              <Avatar>
                <AvatarFallback>{initials(me?.display)}</AvatarFallback>
              </Avatar>
              <div className="hidden text-left leading-tight sm:block">
                <div className="max-w-[12rem] truncate text-sm font-medium text-foreground">
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
