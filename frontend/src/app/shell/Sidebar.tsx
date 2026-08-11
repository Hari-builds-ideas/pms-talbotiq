import * as React from "react";
import { NavLink } from "react-router-dom";
import { PlusCircle } from "lucide-react";
import { navForRole } from "@/app/nav";
import { BRAND, BrandMark } from "@/brand";
import { useAuth } from "@/lib/auth/AuthContext";
import { cn } from "@/lib/utils";

/** The sidebar brand lockup: the Axiom mark + name by default. A white-label
 *  tenant's own logo (PHASE2 L1.5 custom_branding) replaces the mark; a broken or
 *  unreachable tenant logo falls back to the Axiom mark via onError — so a bad
 *  logo URL can never render a broken image or leak alt text over the wordmark. */
function SidebarBrand({
  logoUrl,
  tenantName,
}: {
  logoUrl?: string | null;
  tenantName?: string | null;
}) {
  const [broken, setBroken] = React.useState(false);
  const showTenantLogo = Boolean(logoUrl) && !broken;
  return (
    <span className="flex items-center gap-3">
      {showTenantLogo ? (
        <img
          src={logoUrl as string}
          alt=""
          onError={() => setBroken(true)}
          className="h-10 w-10 rounded-xl object-contain"
        />
      ) : (
        // The cropped mark fills its frame — render it a proper ~40px tall so it
        // reads as a real logo (not a speck) next to the wordmark text.
        <BrandMark className="h-10 w-auto shrink-0" />
      )}
      <span className="leading-tight">
        <span className="block text-base font-bold tracking-tight text-foreground">
          {showTenantLogo ? (tenantName ?? BRAND.shortName) : BRAND.shortName}
        </span>
        <span className="block text-[11px] text-sidebar-muted">
          Performance Management System
        </span>
      </span>
    </span>
  );
}

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
    // Below lg the sidebar OVERLAYS the content instead of sitting beside it.
    // Inline, its w-64 is 256 of a phone's 390px and the page is left with ~130 —
    // enough for the dashboard stat cards to land on top of each other. From lg up
    // this is `relative` again, i.e. exactly the desktop layout it has always had.
    <aside className="fixed inset-y-0 left-0 z-40 flex h-full w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar shadow-xl lg:relative lg:z-auto lg:shadow-none">
      {/* Brand lockup (see SidebarBrand — tenant logo overrides, with fallback). */}
      <div className="flex h-16 items-center px-5">
        <SidebarBrand
          logoUrl={me?.tenant_branding?.logo_url}
          tenantName={me?.tenant_name}
        />
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
