import * as React from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ArrowUpRight, Bot, Plus, Send, Sparkles, User as UserIcon } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { aiApi } from "@/lib/api/endpoints";
import { mapApiError } from "@/lib/errors";
import { AIUnavailable, aiUnavailableCode, type AIUnavailableCode } from "@/components/AIUnavailable";
import { useAuth } from "@/lib/auth/AuthContext";
import { FeatureGate } from "@/components/FeatureGate";
import { cn } from "@/lib/utils";
import type { ChatPlan, ChatProposal } from "@/lib/types";
import { HowToUse, starterPrompts } from "./HowToUse";
import { ProposalCard } from "./ProposalCard";
import { PlanChecklist } from "./PlanChecklist";

interface ChatContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
  toggle: () => void;
  /** Panel width in px (persisted) — the shell reads it to shrink content beside the chat. */
  width: number;
  setWidth: (w: number) => void;
}
const ChatContext = React.createContext<ChatContextValue | null>(null);

export function useChatPanel() {
  const ctx = React.useContext(ChatContext);
  if (!ctx) throw new Error("useChatPanel must be used within <ChatProvider>");
  return ctx;
}

// ── panel width (E1: resizable, persisted) ────────────────────────────────────
const CHAT_WIDTH_KEY = "pms.chat.width";
const CHAT_MIN_W = 320;
const CHAT_MAX_W = 720;
const CHAT_DEFAULT_W = 400;
const clampWidth = (w: number) => Math.min(CHAT_MAX_W, Math.max(CHAT_MIN_W, Math.round(w)));

function initialWidth(): number {
  try {
    const saved = Number(localStorage.getItem(CHAT_WIDTH_KEY));
    if (Number.isFinite(saved) && saved > 0) return clampWidth(saved);
  } catch {
    /* storage unavailable → default */
  }
  return CHAT_DEFAULT_W;
}

interface Turn {
  role: "user" | "assistant";
  text: string;
  status?: "ok" | "blocked" | "proposal" | "plan";
  data?: unknown;
  proposal?: ChatProposal;
  plan?: ChatPlan;
  /** A navigation answer ("open the draft") — rendered as an Open button. */
  deeplink?: string;
}

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  // E1: width lives on the provider so the shell can shrink content beside the
  // panel (true side-by-side copilot), persisted so the user's choice sticks.
  const [width, setWidthRaw] = React.useState(initialWidth);
  const setWidth = React.useCallback((w: number) => {
    const clamped = clampWidth(w);
    setWidthRaw(clamped);
    try {
      localStorage.setItem(CHAT_WIDTH_KEY, String(clamped));
    } catch {
      /* storage unavailable → width is session-only */
    }
  }, []);
  const value = React.useMemo(
    () => ({ open, setOpen, toggle: () => setOpen((v) => !v), width, setWidth }),
    [open, width, setWidth],
  );
  return (
    <ChatContext.Provider value={value}>
      {children}
      <ChatSheet />
    </ChatContext.Provider>
  );
}

/** E1: the drag handle on the panel's left edge — pointer-driven, clamped by setWidth. */
function ResizeHandle({ onResize }: { onResize: (w: number) => void }) {
  const onPointerDown = (e: React.PointerEvent) => {
    e.preventDefault();
    const move = (ev: PointerEvent) => onResize(window.innerWidth - ev.clientX);
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      document.body.style.cursor = "";
    };
    document.body.style.cursor = "col-resize";
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize chat panel"
      onPointerDown={onPointerDown}
      className="absolute inset-y-0 left-0 z-10 w-1.5 cursor-col-resize touch-none select-none transition-colors hover:bg-primary/30 active:bg-primary/40"
    />
  );
}

const CHAT_SESSION_KEY = "pms.chat.session";

function ChatSheet() {
  const { open, setOpen, width, setWidth } = useChatPanel();
  const { hasFeature, atLeast } = useAuth();
  /** Only a manager and above has anybody else to ask about — the one limit that
      genuinely differs by role, so the only one the help text branches on. */
  const canSeeTeam = atLeast("MANAGER");
  const [turns, setTurns] = React.useState<Turn[]>([]);
  const [input, setInput] = React.useState("");
  // WHICH unavailable state, not just whether (B3): switched off, never
  // configured, out of budget and provider-down need different answers.
  const [unavailable, setUnavailable] = React.useState<AIUnavailableCode | null>(null);
  const sessionId = React.useRef<string | undefined>(undefined);
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const inputRef = React.useRef<HTMLTextAreaElement>(null);

  const rememberSession = React.useCallback((id: string) => {
    sessionId.current = id;
    try {
      localStorage.setItem(CHAT_SESSION_KEY, id);
    } catch {
      /* storage unavailable → session is tab-only */
    }
  }, []);

  // C2: resume the conversation across full reloads. The 24h server session is the
  // source of truth — rehydrate its turns (text history; plans re-render as their
  // summaries). An expired/foreign id 404s server-side → start fresh, key cleared.
  React.useEffect(() => {
    let stored: string | null = null;
    try {
      stored = localStorage.getItem(CHAT_SESSION_KEY);
    } catch {
      stored = null;
    }
    if (!stored) return;
    let cancelled = false;
    aiApi
      .getSession(stored)
      .then((s) => {
        if (cancelled) return;
        sessionId.current = s.id;
        setTurns(
          (s.turns ?? [])
            .filter((t) => (t.text ?? "").trim())
            .map((t) => ({ role: t.role === "user" ? "user" : "assistant", text: t.text }) as Turn),
        );
      })
      .catch(() => {
        try {
          localStorage.removeItem(CHAT_SESSION_KEY);
        } catch {
          /* ignore */
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // AGENT_UX_V3 §A — ONE send path. /ai/chat answers reads and, for a write intent,
  // returns an inert PLAN (status:"plan") the human approves step by step. Session id
  // is threaded across turns for short-term memory.
  const mutation = useMutation({
    mutationFn: (q: string) => aiApi.chat(q, sessionId.current),
    onSuccess: (res) => {
      if (res.session_id) rememberSession(res.session_id);
      setTurns((t) => [
        ...t,
        {
          role: "assistant",
          text: res.answer,
          status: res.status,
          data: res.data,
          proposal: res.proposal,
          plan: res.plan,
          deeplink: res.deeplink,
        },
      ]);
    },
    onError: (err) => {
      const code = aiUnavailableCode(err);
      if (code) {
        setUnavailable(code);
        return;
      }
      const mapped = mapApiError(err);
      if (mapped.kind === "ai_unavailable") {
        // No code on the body — an older server, or a 503 from somewhere else in
        // the stack. Fall back to the least presumptuous of the four.
        setUnavailable("ai_not_configured");
      } else {
        setTurns((t) => [
          ...t,
          { role: "assistant", text: mapped.message, status: "blocked" },
        ]);
      }
    },
  });
  const busy = mutation.isPending;

  React.useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, mutation.isPending]);

  // §6: auto-grow the textarea from 1 row up to ~6, then scroll. Reset to auto so
  // it can SHRINK when text is deleted, then clamp to the max height.
  const MAX_ROWS = 6;
  React.useLayoutEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    const cs = window.getComputedStyle(el);
    const line = parseFloat(cs.lineHeight) || 20;
    const pad = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
    const maxH = line * MAX_ROWS + pad;
    el.style.height = `${Math.min(el.scrollHeight, maxH)}px`;
    el.style.overflowY = el.scrollHeight > maxH ? "auto" : "hidden";
  }, [input]);

  /** Send `text` as a turn. Takes the text rather than reading `input`, so a starter
      chip can send on the click that sets it — a `setInput` then `submit()` would send
      the previous value, because state has not landed yet. */
  const ask = React.useCallback(
    (text: string) => {
      const q = text.trim();
      if (!q || unavailable) return;
      setTurns((t) => [...t, { role: "user", text: q }]);
      setInput("");
      mutation.mutate(q);
    },
    [unavailable, mutation],
  );

  const submit = React.useCallback(() => ask(input), [ask, input]);

  function send(e: React.FormEvent) {
    e.preventDefault();
    submit();
  }

  // §6: "New chat" — clear local turns AND drop the session id so the NEXT message
  // starts a fresh server session (no prior messages / entities carried over). A
  // pronoun follow-up after this has no memory of the previous thread.
  const newChat = React.useCallback(() => {
    setTurns([]);
    setInput("");
    setUnavailable(null);
    sessionId.current = undefined;
    try {
      localStorage.removeItem(CHAT_SESSION_KEY);
    } catch {
      /* storage unavailable → nothing to clear */
    }
    inputRef.current?.focus();
  }, []);

  return (
    <Sheet open={open} onOpenChange={setOpen} modal={false}>
      {/* Non-blocking dockable copilot (E2): no overlay + non-modal so the rest of the
          PMS stays usable while the assistant is open; interacting with the app or
          navigating never dismisses it (close via the X or the Ask-AI toggle). The shell
          shrinks content by `width` so page + chat sit truly side by side. E1: the left
          edge is a drag handle; width is clamped 320–720 and persisted. */}
      <SheetContent
        side="right"
        overlay={false}
        onInteractOutside={(e) => e.preventDefault()}
        className="w-full"
        style={{ width, maxWidth: "100vw" }}
      >
        <ResizeHandle onResize={setWidth} />
        <SheetHeader>
          {/* The panel is resizable down to 320px, so the header has to hold a title,
              two controls and the close button in very little room. `whitespace-nowrap`
              on the title and `shrink-0` on the controls is what stops "AI Assistant"
              wrapping onto two lines when it gets tight — which it did, and it made the
              whole panel look unfinished. */}
          <div className="flex items-center justify-between gap-2 pr-8">
            <SheetTitle className="flex min-w-0 items-center gap-2 whitespace-nowrap">
              <Sparkles className="h-4 w-4 shrink-0 text-ai" />
              AI Assistant
            </SheetTitle>
            <div className="flex shrink-0 items-center gap-0.5">
              <HowToUse canSeeTeam={canSeeTeam} />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={newChat}
                disabled={turns.length === 0 && !input}
                className="h-7 gap-1 whitespace-nowrap px-2 text-xs text-muted-foreground"
                aria-label="Start a new chat"
              >
                <Plus className="h-3.5 w-3.5" /> New chat
              </Button>
            </div>
          </div>
          <SheetDescription>
            Ask questions or plan multi-step tasks — I propose, you approve each step.
            Nothing runs without your OK.
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
              {unavailable && <AIUnavailable code={unavailable} />}
              {turns.length === 0 && !unavailable && (
                <div className="space-y-4 pt-8 text-center">
                  <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-ai-subtle text-ai">
                    <Bot className="h-5 w-5" />
                  </div>
                  <div className="space-y-1">
                    <p className="text-sm font-medium">
                      Ask about {canSeeTeam ? "your team" : "your goals"}
                    </p>
                    <p className="mx-auto max-w-[16rem] text-xs leading-relaxed text-muted-foreground">
                      Goals, KPIs, scores and reviews — always within your access.
                    </p>
                  </div>
                  {/* One click sends. A chip that only fills the box makes the user
                      press Enter to find out whether it was a good question; sending
                      shows them, which is the point of an example. */}
                  <div className="flex flex-col items-stretch gap-1.5 px-2 text-left">
                    {starterPrompts(canSeeTeam).map((s) => (
                      <button
                        key={s}
                        type="button"
                        onClick={() => ask(s)}
                        className="group flex items-center justify-between gap-2 rounded-lg border border-border bg-card px-3 py-2 text-xs text-foreground transition-colors hover:border-ai/40 hover:bg-ai-subtle"
                      >
                        <span>{s}</span>
                        <Send className="h-3 w-3 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                      </button>
                    ))}
                  </div>
                  {/* The header's help affordance is an icon for want of room. Here
                      there is room, and here is where a new user actually is. */}
                  <div className="flex justify-center pt-1">
                    <HowToUse canSeeTeam={canSeeTeam} variant="link" />
                  </div>
                </div>
              )}

              {turns.map((turn, i) => (
                <ChatBubble key={i} turn={turn} onSuggest={setInput} />
              ))}

              {busy && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Bot className="h-4 w-4 text-ai" />
                  <span className="flex gap-1">
                    <Dot /> <Dot /> <Dot />
                  </span>
                </div>
              )}
            </div>

            <form onSubmit={send} className="flex items-end gap-2 border-t border-border p-4">
              {/* §6: auto-growing textarea. Enter submits, Shift+Enter = newline; it
                  grows from 1 row up to ~6 then scrolls (height managed in an effect). */}
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    submit();
                  }
                }}
                rows={1}
                placeholder="Ask, or describe a multi-step task…"
                disabled={Boolean(unavailable)}
                aria-label="Chat message"
                className={cn(
                  "flex-1 resize-none rounded-md border border-input bg-input-background px-3 py-2 text-sm leading-5 transition-colors",
                  "placeholder:text-muted-foreground",
                  "focus-visible:outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:bg-card",
                  "disabled:cursor-not-allowed disabled:opacity-50",
                )}
              />
              <Button type="submit" size="icon" disabled={Boolean(unavailable) || !input.trim()}>
                <Send className="h-4 w-4" />
              </Button>
            </form>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

function ChatBubble({ turn, onSuggest }: { turn: Turn; onSuggest?: (text: string) => void }) {
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
        <p className="whitespace-pre-wrap break-words">{turn.text}</p>
        {turn.deeplink && <DeeplinkButton to={turn.deeplink} />}
        {turn.proposal && <ProposalCard proposal={turn.proposal} />}
        {turn.plan && <PlanChecklist plan={turn.plan} onSuggest={onSuggest} />}
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

function Dot() {
  return (
    <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
  );
}

/** A navigation answer's Open button — actually navigates (never chat input). */
function DeeplinkButton({ to }: { to: string }) {
  const navigate = useNavigate();
  return (
    <Button size="sm" variant="outline" className="mt-1" onClick={() => navigate(to)}>
      Open <ArrowUpRight className="h-3.5 w-3.5" />
    </Button>
  );
}
