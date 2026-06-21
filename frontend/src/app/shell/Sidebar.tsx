import { NavLink } from "react-router-dom";
import { NAV, APP_ICON } from "@/app/nav";
import { useAuth } from "@/lib/auth/AuthContext";
import { cn } from "@/lib/utils";

/** Fixed dark sidebar with role-filtered, grouped navigation. */
export function Sidebar() {
  const { atLeast, me } = useAuth();

  return (
    <aside className="flex h-full w-60 shrink-0 flex-col bg-sidebar text-sidebar-foreground">
      <div className="flex h-14 items-center gap-2.5 px-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-sidebar-accent text-white">
          <APP_ICON className="h-4 w-4" />
        </div>
        <div className="leading-tight">
          <div className="text-sm font-semibold text-white">Talbotiq</div>
          <div className="text-2xs text-sidebar-muted">PMS Admin Hub</div>
        </div>
      </div>

      <nav aria-label="Primary" className="flex-1 space-y-5 overflow-y-auto scrollbar-thin px-3 py-4">
        {NAV.map((section) => {
          const items = section.items.filter((i) => atLeast(i.minRole));
          if (items.length === 0) return null;
          return (
            <div key={section.title}>
              <div className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-sidebar-muted">
                {section.title}
              </div>
              <ul className="space-y-0.5">
                {items.map((item) => (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      end={item.end}
                      className={({ isActive }) =>
                        cn(
                          "group relative flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm font-medium transition-colors",
                          isActive
                            ? "bg-sidebar-accent/15 text-white before:absolute before:left-0 before:top-1.5 before:bottom-1.5 before:w-0.5 before:rounded-full before:bg-sidebar-accent"
                            : "text-sidebar-foreground/80 hover:bg-white/5 hover:text-white",
                        )
                      }
                    >
                      {({ isActive }) => (
                        <>
                          <item.icon
                            className={cn(
                              "h-4 w-4 shrink-0",
                              isActive
                                ? "text-sidebar-accent"
                                : "text-sidebar-muted group-hover:text-white",
                            )}
                          />
                          <span className="truncate">{item.label}</span>
                        </>
                      )}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </nav>

      <div className="border-t border-sidebar-border px-5 py-3 text-2xs text-sidebar-muted">
        v1 · {me?.tenant_name ?? "Talbotiq"}
      </div>
    </aside>
  );
}
