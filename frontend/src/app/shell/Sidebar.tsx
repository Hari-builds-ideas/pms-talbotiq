import { NavLink } from "react-router-dom";
import { PlusCircle } from "lucide-react";
import { navForRole } from "@/app/nav";
import { BRAND, BrandMark } from "@/brand";
import { useAuth } from "@/lib/auth/AuthContext";
import { cn } from "@/lib/utils";

/** Opens the ⌘K command palette (reuses its global keydown listener) — the
 *  "Quick Actions" surface (jump to any destination / search people / Ask AI). */
function openCommandPalette() {
  document.dispatchEvent(
    new KeyboardEvent("keydown", { key: "k", metaKey: true, ctrlKey: true }),
  );
}

/** Light sidebar with the TalbotIQ brand lockup, sectioned role-filtered nav
 *  (brand-green active state), and Quick Actions pinned bottom-left. */
export function Sidebar() {
  const { me } = useAuth();
  // Visibility is a pure function of role (navForRole) — the same source the nav
  // tests assert. A role only ever sees the sections/items it can use.
  const sections = navForRole(me?.role ?? "EMPLOYEE");

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar">
      {/* Brand lockup — a tenant logo (PHASE2 L1.5 branding hook) replaces the
          default mark when the plan includes custom_branding. */}
      <div className="flex h-16 items-center gap-2.5 px-5">
        {me?.tenant_branding?.logo_url ? (
          <img
            src={me.tenant_branding.logo_url}
            alt="Organization logo"
            className="h-9 w-9 rounded-xl object-contain"
          />
        ) : (
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10">
            <BrandMark className="h-6 w-6" />
          </div>
        )}
        <div className="leading-tight">
          <div className="text-base font-bold tracking-tight text-foreground">{BRAND.shortName}</div>
          <div className="text-[11px] text-sidebar-muted">Performance Management System</div>
        </div>
      </div>

      <nav aria-label="Primary" className="flex-1 space-y-6 overflow-y-auto scrollbar-thin px-3 py-3">
        {sections.map((section, i) => (
          <div key={section.title || `section-${i}`}>
            {section.title ? (
              <div className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-wider text-sidebar-muted">
                {section.title}
              </div>
            ) : null}
            <ul className="space-y-0.5">
              {section.items.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) =>
                      cn(
                        "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                        isActive
                          ? "bg-primary/10 text-primary before:absolute before:left-0 before:top-1.5 before:bottom-1.5 before:w-1 before:rounded-full before:bg-primary"
                          : "text-sidebar-foreground hover:bg-secondary hover:text-foreground",
                      )
                    }
                  >
                    {({ isActive }) => (
                      <>
                        <item.icon
                          className={cn(
                            "h-[18px] w-[18px] shrink-0",
                            isActive ? "text-primary" : "text-sidebar-muted group-hover:text-foreground",
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
        ))}
      </nav>

      {/* Quick Actions — pinned bottom-left */}
      <div className="border-t border-sidebar-border p-3">
        <button
          type="button"
          onClick={openCommandPalette}
          className="flex w-full items-center justify-center gap-2 rounded-lg border border-sidebar-border bg-card px-3 py-2.5 text-sm font-semibold text-foreground shadow-xs transition-colors hover:bg-secondary"
        >
          <PlusCircle className="h-4 w-4 text-primary" />
          Quick Actions
        </button>
        <div className="mt-2 truncate px-1 text-[11px] text-sidebar-muted">
          {me?.tenant_name ?? BRAND.name}
        </div>
      </div>
    </aside>
  );
}
