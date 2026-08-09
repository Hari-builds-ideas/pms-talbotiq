import { HelpCircle } from "lucide-react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Plain-language "what this can and can't do".
 *
 * The assistant's limits are the part users discover by hitting them — asking about
 * somebody outside their scope, or expecting a change to just happen. Saying so before
 * they ask costs one click and saves the confusing answer.
 *
 * Two triggers, because the header has no room for a third piece of text. At 320px the
 * panel is already carrying a title, "New chat" and the close button; a labelled help
 * button pushed "AI Assistant" onto two lines and made the whole header look cheap. So
 * the header gets an icon, and the empty state — which has room and is where a new user
 * actually is — gets the words.
 */
export function HowToUse({
  canSeeTeam,
  variant = "icon",
}: {
  canSeeTeam: boolean;
  variant?: "icon" | "link";
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          title="How to use the assistant"
          aria-label="How to use the assistant"
          className={cn(
            "text-muted-foreground",
            variant === "icon"
              ? "h-7 w-7 shrink-0 p-0"
              : "h-auto gap-1 px-2 py-1 text-xs font-normal underline-offset-4 hover:underline",
          )}
        >
          <HelpCircle className="h-3.5 w-3.5" />
          {variant === "link" && <span>How to use</span>}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 text-sm">
        <p className="text-sm font-medium">What I can do</p>
        <ul className="mt-2 space-y-1.5 text-muted-foreground">
          <li className="flex gap-2">
            <Dot /> Summarise goals, KPIs, cycle scores and review status
          </li>
          {canSeeTeam ? (
            <>
              <li className="flex gap-2">
                <Dot /> Diagnose who needs help, and why
              </li>
              <li className="flex gap-2">
                <Dot /> Rank or compare your team, and count who&rsquo;s behind
              </li>
              <li className="flex gap-2">
                <Dot /> Answer open questions &mdash; &ldquo;who improved most since last
                cycle?&rdquo;
              </li>
            </>
          ) : (
            <li className="flex gap-2">
              <Dot /> Tell you how you&rsquo;re tracking this cycle
            </li>
          )}
          <li className="flex gap-2">
            <Dot /> Prepare recognition, check-ins and review drafts for your approval
          </li>
        </ul>

        <div className="my-3 h-px bg-border" />

        <p className="text-sm font-medium">What I can&rsquo;t do</p>
        <ul className="mt-2 space-y-1.5 text-muted-foreground">
          <li className="flex gap-2">
            <Dot muted /> Change anything on my own &mdash; you approve every action first
          </li>
          <li className="flex gap-2">
            <Dot muted />
            {canSeeTeam
              ? "See people outside your access"
              : "See anyone else's data — only your own"}
          </li>
          <li className="flex gap-2">
            <Dot muted /> Answer questions that aren&rsquo;t about performance
          </li>
        </ul>

        <p className="mt-3 border-t border-border pt-3 text-xs text-muted-foreground">
          Every number comes from your real data. If there isn&rsquo;t any, I&rsquo;ll say
          so rather than guess.
        </p>
      </PopoverContent>
    </Popover>
  );
}

/** A small aligned bullet — a list marker that lines up with wrapped text. */
function Dot({ muted = false }: { muted?: boolean }) {
  return (
    <span
      aria-hidden
      className={cn(
        "mt-[0.45rem] h-1 w-1 shrink-0 rounded-full",
        muted ? "bg-muted-foreground/40" : "bg-ai",
      )}
    />
  );
}

/**
 * Example prompts for the empty chat, as one-click chips.
 *
 * They set expectations by example: a new user who clicks one gets a good answer and
 * learns the shape of a question this thing is good at. "What can you do?" is first
 * because it is the cheapest possible orientation — answered from the role, with no
 * model call behind it.
 */
export function starterPrompts(canSeeTeam: boolean): string[] {
  return canSeeTeam
    ? [
        "What can you do?",
        "Who's at risk on my team?",
        "Who improved most since last cycle?",
        "How many of my reports are behind pace?",
      ]
    : [
        "What can you do?",
        "How am I doing this cycle?",
        "What are my goals?",
        "Do I need help this cycle?",
      ];
}
