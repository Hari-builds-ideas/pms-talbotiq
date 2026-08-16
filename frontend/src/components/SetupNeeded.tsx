import * as React from "react";
import { Link } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import { ArrowRight, Inbox } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/EmptyState";

/**
 * The empty state for a module that cannot be used YET, because something
 * upstream does not exist.
 *
 * This is a different situation from "no data", and the ordinary EmptyState
 * handles it badly. A brand-new tenant has no people, no reporting lines and no
 * performance cycle, and most of this product hangs off all three. What the
 * pages did was show "No reviews yet — create a review for someone on your team"
 * and then hide the button, because the code already knew there was no cycle to
 * create one in. The admin was told to do something, given nothing to do it
 * with, and left to guess which of the other screens held the missing piece.
 *
 * So this names the blocker and offers the fix in place. A new admin should
 * never have to guess what to do next.
 */

export interface Prerequisite {
  /** What is missing, in the user's words: "a performance cycle". */
  label: string;
  /** Fix it here — preferred, because it keeps the person on the page they wanted. */
  onFix?: () => void;
  /** Or send them to the screen that owns it. */
  to?: string;
  /**
   * Whether this person can fix it. Default true. When false, no button is
   * offered: a link to a page that will 403 is worse than no link.
   */
  canFix?: boolean;
}

interface SetupNeededProps {
  icon?: LucideIcon;
  /** What this module is for, in one line, so the page is not only a blocker. */
  title: string;
  needs: Prerequisite;
  /** Anything else worth saying once. */
  description?: React.ReactNode;
}

export function SetupNeeded({
  icon = Inbox,
  title,
  needs,
  description,
}: SetupNeededProps) {
  const canFix = needs.canFix !== false;
  const label = `Set up ${needs.label}`;

  let action: React.ReactNode;
  if (!canFix) {
    action = undefined;
  } else if (needs.onFix) {
    action = (
      <Button onClick={needs.onFix}>
        {label}
        <ArrowRight className="ml-1.5 h-4 w-4" aria-hidden />
      </Button>
    );
  } else if (needs.to) {
    action = (
      <Button asChild>
        <Link to={needs.to}>
          {label}
          <ArrowRight className="ml-1.5 h-4 w-4" aria-hidden />
        </Link>
      </Button>
    );
  }

  return (
    <EmptyState
      icon={icon}
      title={title}
      description={
        <>
          This needs {needs.label} first.
          {description ? <> {description}</> : null}
          {canFix ? null : (
            <>
              {" "}
              Ask an admin to set it up — your account cannot.
            </>
          )}
        </>
      }
      action={action}
    />
  );
}
