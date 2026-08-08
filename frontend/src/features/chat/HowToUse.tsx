import { HelpCircle } from "lucide-react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Button } from "@/components/ui/button";

/**
 * Plain-language "what this can and can't do", next to New chat.
 *
 * The assistant's limits are the part users discover by hitting them — asking about
 * somebody outside their scope, or expecting a change to just happen. Saying so before
 * they ask costs one click and saves the confusing answer.
 *
 * Deliberately role-aware in only one place (who you can ask about), because that is the
 * only limit that actually differs between a manager and an employee.
 */
export function HowToUse({ canSeeTeam }: { canSeeTeam: boolean }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 gap-1 text-xs text-muted-foreground"
          aria-label="How to use the assistant"
        >
          <HelpCircle className="h-3.5 w-3.5" /> How to use
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 text-sm">
        <p className="font-medium">What I can do</p>
        <ul className="mt-1.5 list-disc space-y-1 pl-4 text-muted-foreground">
          <li>Summarise goals, KPIs, cycle scores and review status</li>
          {canSeeTeam ? (
            <>
              <li>Diagnose who needs help, and why</li>
              <li>Rank or compare your team, and count who&rsquo;s behind</li>
              <li>Answer open questions — &ldquo;who improved most since last cycle?&rdquo;</li>
            </>
          ) : (
            <li>Tell you how you&rsquo;re tracking this cycle</li>
          )}
          <li>Prepare recognition, check-ins and review drafts for your approval</li>
        </ul>

        <p className="mt-3 font-medium">What I can&rsquo;t do</p>
        <ul className="mt-1.5 list-disc space-y-1 pl-4 text-muted-foreground">
          <li>Change anything on my own — you approve every action first</li>
          <li>
            {canSeeTeam
              ? "See people outside your access"
              : "See anyone else's data — only your own"}
          </li>
          <li>Answer questions that aren&rsquo;t about performance</li>
        </ul>

        <p className="mt-3 text-xs text-muted-foreground">
          Every number comes from your real data. If there isn&rsquo;t any, I&rsquo;ll say
          so rather than guess.
        </p>
      </PopoverContent>
    </Popover>
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
