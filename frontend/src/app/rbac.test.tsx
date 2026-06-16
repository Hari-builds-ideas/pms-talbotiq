import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ROLE_RANK } from "@/lib/enums";

// Mutable mock of the auth context shared by the gates under test.
let authState: { me: { role: string } | null; hasFeature: (k: string) => boolean };
vi.mock("@/lib/auth/AuthContext", () => ({
  useAuth: () => authState,
}));

// Imported AFTER the mock is declared (vi.mock is hoisted).
import { RoleGate } from "@/app/guards";
import { FeatureGate } from "@/components/FeatureGate";

function setAuth(role: string | null, features: Record<string, boolean> = {}) {
  authState = {
    me: role ? { role } : null,
    hasFeature: (k: string) => Boolean(features[k]),
  };
}

const wrap = (ui: React.ReactNode) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe("ROLE_RANK ordering", () => {
  it("orders the four roles by breadth", () => {
    expect(ROLE_RANK.EMPLOYEE).toBeLessThan(ROLE_RANK.MANAGER);
    expect(ROLE_RANK.MANAGER).toBeLessThan(ROLE_RANK.HRBP);
    expect(ROLE_RANK.HRBP).toBeLessThan(ROLE_RANK.ADMIN);
  });
});

describe("RoleGate", () => {
  it("renders children when the role meets the minimum", () => {
    setAuth("HRBP");
    wrap(<RoleGate min="MANAGER"><div>secret</div></RoleGate>);
    expect(screen.getByText("secret")).toBeInTheDocument();
  });

  it("shows the 403 page (not the content) when below the minimum", () => {
    setAuth("EMPLOYEE");
    wrap(<RoleGate min="MANAGER"><div>secret</div></RoleGate>);
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
    expect(screen.getByText(/don't have access/i)).toBeInTheDocument();
  });

  it("blocks a manager from an ADMIN-only area", () => {
    setAuth("MANAGER");
    wrap(<RoleGate min="ADMIN"><div>admin-only</div></RoleGate>);
    expect(screen.queryByText("admin-only")).not.toBeInTheDocument();
  });
});

describe("FeatureGate", () => {
  it("renders children when the feature is unlocked", () => {
    setAuth("ADMIN", { career_roadmap: true });
    wrap(<FeatureGate feature="career_roadmap"><div>ai-thing</div></FeatureGate>);
    expect(screen.getByText("ai-thing")).toBeInTheDocument();
  });

  it("shows a premium upsell (never hides) when locked, with an admin upgrade link", () => {
    setAuth("ADMIN", {});
    wrap(<FeatureGate feature="career_roadmap"><div>ai-thing</div></FeatureGate>);
    expect(screen.queryByText("ai-thing")).not.toBeInTheDocument();
    expect(screen.getByText(/upgrade to unlock/i)).toBeInTheDocument();
  });

  it("tells a non-admin to ask their admin (no upgrade link)", () => {
    setAuth("MANAGER", {});
    wrap(<FeatureGate feature="career_roadmap"><div>ai-thing</div></FeatureGate>);
    expect(screen.getByText(/ask your workspace admin/i)).toBeInTheDocument();
    expect(screen.queryByText(/upgrade to unlock/i)).not.toBeInTheDocument();
  });
});
