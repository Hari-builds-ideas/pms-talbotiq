import * as React from "react";
import { cn } from "@/lib/utils";

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        ref={ref}
        className={cn(
          // 16px on a phone, 13px (text-sm) from sm up.
          //
          // iOS Safari zooms the whole page when a focused input's font-size is
          // under 16px, and it does not zoom back out — so tapping one field left
          // the user on a magnified, sideways-scrolling page they had to pinch
          // their way out of. The control is also taller below sm (h-11 = 44px)
          // so it is a legal touch target.
          //
          // The literal text-[16px] is deliberate: this project's Tailwind scale
          // is a compact enterprise one where `base` is 0.875rem = 14px, so
          // `text-base` would still trip the zoom. 16 is a platform threshold,
          // not a design token — it must not move when the scale is retuned.
          "flex h-11 w-full rounded-lg border border-input bg-input-background px-3 py-1 text-[16px] transition-all sm:h-9 sm:text-sm",
          "placeholder:text-muted-foreground",
          "focus-visible:outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:bg-card",
          "disabled:cursor-not-allowed disabled:opacity-50",
          "file:border-0 file:bg-transparent file:text-sm file:font-medium",
          className,
        )}
        {...props}
      />
    );
  },
);
Input.displayName = "Input";

export { Input };
