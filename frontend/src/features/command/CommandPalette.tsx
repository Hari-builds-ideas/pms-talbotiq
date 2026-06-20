import * as React from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Sparkles, User } from "lucide-react";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { NAV } from "@/app/nav";
import { useAuth } from "@/lib/auth/AuthContext";
import { useChatPanel } from "@/features/chat/ChatPanel";
import { orgApi } from "@/lib/api/endpoints";
import { ROLE_LABEL, type Role } from "@/lib/enums";

/**
 * ⌘K / Ctrl-K command palette — wired to REAL data only:
 *  - jump to any nav destination the caller's role can reach (atLeast-filtered);
 *  - search people via /api/org/search (scoped, tenant-isolated);
 *  - open the AI assistant.
 * No mock data, no fabricated actions.
 */
export function CommandPalette() {
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const navigate = useNavigate();
  const { atLeast } = useAuth();
  const chat = useChatPanel();

  // ⌘K (mac) / Ctrl-K (win/linux) toggles the palette.
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // Real people search — only fires at >= 2 chars; tenant-/scope-isolated server-side.
  const people = useQuery({
    queryKey: ["command", "people", query],
    queryFn: () => orgApi.search(query),
    enabled: open && query.trim().length >= 2,
  });

  const navItems = NAV.flatMap((s) => s.items).filter((i) => atLeast(i.minRole));

  function go(to: string) {
    setOpen(false);
    setQuery("");
    navigate(to);
  }

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      {/* shouldFilter on for nav (client filter); people are server-filtered. */}
      <CommandInput placeholder="Search people, or jump to…" value={query} onValueChange={setQuery} />
      <CommandList>
        <CommandEmpty>No matches.</CommandEmpty>

        {(people.data?.results ?? []).length > 0 && (
          <CommandGroup heading="People">
            {people.data!.results.map((p) => (
              <CommandItem key={p.id} value={`person-${p.id}-${p.display}`} onSelect={() => go(`/org?person=${p.id}`)}>
                <User />
                <span className="font-medium">{p.display}</span>
                <span className="ml-auto text-2xs text-muted-foreground">{ROLE_LABEL[p.role as Role]}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}

        <CommandGroup heading="Go to">
          {navItems.map((item) => (
            <CommandItem key={item.to} value={`nav ${item.label}`} onSelect={() => go(item.to)}>
              <item.icon />
              <span>{item.label}</span>
            </CommandItem>
          ))}
        </CommandGroup>

        <CommandGroup heading="Actions">
          <CommandItem
            value="ask ai assistant chat"
            onSelect={() => {
              setOpen(false);
              chat.setOpen(true);
            }}
          >
            <Sparkles />
            <span>Ask the AI assistant</span>
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
