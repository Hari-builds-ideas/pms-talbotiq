import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bot, Check, Send, Sparkles, User as UserIcon } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { aiApi } from "@/lib/api/endpoints";
import { mapApiError } from "@/lib/errors";
import { useAuth } from "@/lib/auth/AuthContext";
import { FeatureGate } from "@/components/FeatureGate";
import { cn } from "@/lib/utils";
import type { ChatProposal } from "@/lib/types";

interface ChatContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
  toggle: () => void;
}
const ChatContext = React.createContext<ChatContextValue | null>(null);

export function useChatPanel() {
  const ctx = React.useContext(ChatContext);
  if (!ctx) throw new Error("useChatPanel must be used within <ChatProvider>");
  return ctx;
}

interface Turn {
  role: "user" | "assistant";
  text: string;
  status?: "ok" | "blocked" | "proposal";
  data?: unknown;
  proposal?: ChatProposal;
}

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  const value = React.useMemo(
    () => ({ open, setOpen, toggle: () => setOpen((v) => !v) }),
    [open],
  );
  return (
    <ChatContext.Provider value={value}>
      {children}
      <ChatSheet />
    </ChatContext.Provider>
  );
}

function ChatSheet() {
  const { open, setOpen } = useChatPanel();
  const { hasFeature } = useAuth();
  const [turns, setTurns] = React.useState<Turn[]>([]);
  const [input, setInput] = React.useState("");
  const [unavailable, setUnavailable] = React.useState(false);
  const scrollRef = React.useRef<HTMLDivElement>(null);

  const mutation = useMutation({
    mutationFn: (q: string) => aiApi.chat(q),
    onSuccess: (res) => {
      setTurns((t) => [
        ...t,
        { role: "assistant", text: res.answer, status: res.status, data: res.data, proposal: res.proposal },
      ]);
    },
    onError: (err) => {
      const mapped = mapApiError(err);
      if (mapped.kind === "ai_unavailable") {
        setUnavailable(true);
      } else {
        setTurns((t) => [
          ...t,
          { role: "assistant", text: mapped.message, status: "blocked" },
        ]);
      }
    },
  });

  React.useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, mutation.isPending]);

  function send(e: React.FormEvent) {
    e.preventDefault();
    const q = input.trim();
    if (!q) return;
    setTurns((t) => [...t, { role: "user", text: q }]);
    setInput("");
    mutation.mutate(q);
  }

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent side="right" className="w-full sm:max-w-md">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-ai" />
            AI Assistant
          </SheetTitle>
          <SheetDescription>
            Read-only and RBAC-scoped — it only answers from what you can already
            see, and never makes changes.
          </SheetDescription>
        </SheetHeader>

        {!hasFeature("chat") ? (
          <div className="p-5">
            <FeatureGate feature="chat">
              <div />
            </FeatureGate>
          </div>
        ) : (
          <>
            <div
              ref={scrollRef}
              className="flex-1 space-y-3 overflow-y-auto scrollbar-thin p-5"
            >
              {unavailable && (
                <Alert variant="ai">
                  <Sparkles />
                  <AlertTitle>Chat not available yet</AlertTitle>
                  <AlertDescription>
                    No AI provider is configured for this tenant. The rest of the
                    Hub works normally.
                  </AlertDescription>
                </Alert>
              )}
              {turns.length === 0 && !unavailable && (
                <div className="space-y-3 pt-6 text-center">
                  <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-ai-subtle text-ai">
                    <Bot className="h-5 w-5" />
                  </div>
                  <p className="text-sm text-muted-foreground">
                    Ask about your team, goals, reviews, or org — within your scope.
                  </p>
                  <div className="flex flex-wrap justify-center gap-1.5">
                    {["How many open reviews do I have?", "Who is at risk on my team?"].map(
                      (s) => (
                        <button
                          key={s}
                          type="button"
                          onClick={() => setInput(s)}
                          className="rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-secondary"
                        >
                          {s}
                        </button>
                      ),
                    )}
                  </div>
                </div>
              )}

              {turns.map((turn, i) => (
                <ChatBubble key={i} turn={turn} />
              ))}

              {mutation.isPending && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Bot className="h-4 w-4 text-ai" />
                  <span className="flex gap-1">
                    <Dot /> <Dot /> <Dot />
                  </span>
                </div>
              )}
            </div>

            <form onSubmit={send} className="flex items-center gap-2 border-t border-border p-4">
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask a question…"
                disabled={unavailable}
                aria-label="Chat message"
              />
              <Button type="submit" size="icon" disabled={unavailable || !input.trim()}>
                <Send className="h-4 w-4" />
              </Button>
            </form>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

function ChatBubble({ turn }: { turn: Turn }) {
  const isUser = turn.role === "user";
  return (
    <div className={cn("flex gap-2.5", isUser && "flex-row-reverse")}>
      <div
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
          isUser ? "bg-primary/10 text-primary" : "bg-ai-subtle text-ai",
        )}
      >
        {isUser ? <UserIcon className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
      </div>
      <div
        className={cn(
          "max-w-[80%] space-y-2 rounded-lg px-3 py-2 text-sm",
          isUser ? "bg-primary text-primary-foreground" : "bg-secondary text-foreground",
        )}
      >
        {turn.status === "blocked" && (
          <Badge variant="warning" className="mb-1">Read-only</Badge>
        )}
        <p className="whitespace-pre-wrap">{turn.text}</p>
        {turn.proposal && <ProposalCard proposal={turn.proposal} />}
        {Array.isArray(turn.data) && turn.data.length > 0 && (
          <ul className="list-disc space-y-0.5 pl-4 text-xs opacity-90">
            {(turn.data as string[]).map((d, i) => (
              <li key={i}>{d}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/**
 * The inline confirm card for a proposed assistant action (RW_BUILD_4). The
 * proposal is inert — nothing happens until the human taps Approve, which calls
 * the execute endpoint (the server re-checks permission + scope and audits). On
 * success we invalidate goals so an open screen reflects the approvals.
 */
function ProposalCard({ proposal }: { proposal: ChatProposal }) {
  const qc = useQueryClient();
  const [phase, setPhase] = React.useState<"pending" | "running" | "done" | "cancelled">("pending");
  const [result, setResult] = React.useState("");

  async function approve() {
    setPhase("running");
    try {
      const r = await aiApi.executeAction(proposal.action, proposal.params);
      void qc.invalidateQueries({ queryKey: ["goals"] });
      const n = r.approved ?? 0;
      const skipped = r.skipped?.length ?? 0;
      setResult(`Approved ${n} goal(s)${skipped ? `, skipped ${skipped}` : ""}.`);
      setPhase("done");
    } catch (err) {
      setResult(mapApiError(err).message);
      setPhase("done");
    }
  }

  if (phase === "cancelled") {
    return <p className="mt-1 text-2xs italic opacity-80">Cancelled — nothing was changed.</p>;
  }
  if (phase === "done") {
    return (
      <p className="mt-1 flex items-center gap-1 text-2xs">
        <Check className="h-3 w-3 text-success" /> {result}
      </p>
    );
  }
  return (
    <div className="mt-1.5 rounded-md border border-ai/30 bg-card/60 p-2 text-xs text-foreground">
      <ul className="mb-2 list-disc space-y-0.5 pl-4">
        {proposal.preview.slice(0, 8).map((p, i) => (
          <li key={i}>
            {String(p.goal ?? "")}
            {p.employee ? <span className="opacity-70"> · {String(p.employee)}</span> : null}
          </li>
        ))}
        {proposal.preview.length > 8 && <li className="opacity-70">…and {proposal.preview.length - 8} more</li>}
      </ul>
      <div className="flex gap-2">
        <Button size="sm" onClick={approve} loading={phase === "running"}>Approve</Button>
        <Button size="sm" variant="outline" onClick={() => setPhase("cancelled")}>Cancel</Button>
      </div>
    </div>
  );
}

function Dot() {
  return (
    <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
  );
}
