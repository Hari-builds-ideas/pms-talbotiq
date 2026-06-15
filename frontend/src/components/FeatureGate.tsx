import * as React from "react";
import { Link } from "react-router-dom";
import { Lock, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/auth/AuthContext";
import { FEATURE_META, type FeatureKey } from "@/lib/enums";
import { cn } from "@/lib/utils";

interface FeatureGateProps {
  feature: FeatureKey;
  children: React.ReactNode;
  /** Render a compact inline lock chip instead of a full card. */
  compact?: boolean;
  className?: string;
}

/**
 * Renders children when the feature is unlocked; otherwise a premium-locked
 * upsell (NEVER an error, NEVER silently hidden — per the contract). Admins get
 * a direct upgrade link; other roles see a "managed by your admin" note.
 */
export function FeatureGate({
  feature,
  children,
  compact,
  className,
}: FeatureGateProps) {
  const { hasFeature, me } = useAuth();
  if (hasFeature(feature)) return <>{children}</>;

  const meta = FEATURE_META[feature];
  const isAdmin = me?.role === "ADMIN";

  if (compact) {
    return (
      <Badge variant="premium" className={cn("gap-1", className)}>
        <Lock className="h-3 w-3" />
        Upgrade to unlock
      </Badge>
    );
  }

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-premium/40 bg-premium-subtle/50 px-6 py-12 text-center",
        className,
      )}
    >
      <div className="flex h-11 w-11 items-center justify-center rounded-full bg-premium/15 text-premium">
        <Sparkles className="h-5 w-5" aria-hidden />
      </div>
      <div className="space-y-1">
        <div className="flex items-center justify-center gap-2">
          <p className="text-md font-semibold text-foreground">{meta.label}</p>
          <Badge variant="premium" className="gap-1">
            <Lock className="h-3 w-3" /> Premium
          </Badge>
        </div>
        <p className="mx-auto max-w-md text-sm text-muted-foreground">
          {meta.description} This is a Full AI feature.
        </p>
      </div>
      {isAdmin ? (
        <Button asChild variant="premium" size="sm">
          <Link to="/admin/billing">Upgrade to unlock</Link>
        </Button>
      ) : (
        <p className="text-xs text-muted-foreground">
          Ask your workspace admin to upgrade to Full AI.
        </p>
      )}
    </div>
  );
}
