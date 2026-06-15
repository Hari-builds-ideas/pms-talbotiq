import { Toaster as Sonner } from "sonner";

type ToasterProps = React.ComponentProps<typeof Sonner>;

/** App toaster — aria-live region for action feedback. */
function Toaster(props: ToasterProps) {
  return (
    <Sonner
      position="bottom-right"
      toastOptions={{
        classNames: {
          toast:
            "group toast group-[.toaster]:bg-card group-[.toaster]:text-foreground group-[.toaster]:border-border group-[.toaster]:shadow-md group-[.toaster]:rounded-lg",
          description: "group-[.toast]:text-muted-foreground",
          actionButton:
            "group-[.toast]:bg-primary group-[.toast]:text-primary-foreground",
          cancelButton:
            "group-[.toast]:bg-secondary group-[.toast]:text-secondary-foreground",
          error: "group-[.toaster]:border-danger/30",
          success: "group-[.toaster]:border-success/30",
          warning: "group-[.toaster]:border-warning/40",
        },
      }}
      {...props}
    />
  );
}

export { Toaster };
export { toast } from "sonner";
