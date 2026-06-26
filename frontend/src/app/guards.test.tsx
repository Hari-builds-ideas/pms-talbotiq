/**
 * AuthGuard — the front-door auth enforcement. Proves an unauthenticated visitor
 * is sent to /login (never sees protected content), the bootstrap shows a loader
 * (not the app) while it resolves, and only an authenticated user is let through.
 * This is the durable guard behind "login must ask for credentials" (BUG 2): the
 * served app enforces auth client-side AND the server 401s — a fresh session can
 * never walk into the app.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

// Mutable auth status driven per test (vi.hoisted so the mock factory can close over it).
const auth = vi.hoisted(() => ({ status: "unauthenticated" as "loading" | "authenticated" | "unauthenticated" }));
vi.mock("@/lib/auth/AuthContext", () => ({
  useAuth: () => ({ status: auth.status, me: null }),
}));

import { AuthGuard } from "@/app/guards";

function renderAt(path = "/goals") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<div>LOGIN FORM</div>} />
        <Route
          path="/goals"
          element={
            <AuthGuard>
              <div>PROTECTED CONTENT</div>
            </AuthGuard>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("AuthGuard", () => {
  it("redirects an unauthenticated user to /login and hides protected content", () => {
    auth.status = "unauthenticated";
    renderAt();
    expect(screen.getByText("LOGIN FORM")).toBeInTheDocument();
    expect(screen.queryByText("PROTECTED CONTENT")).toBeNull();
  });

  it("shows a loader (not the app) while the session is still bootstrapping", () => {
    auth.status = "loading";
    renderAt();
    expect(screen.queryByText("PROTECTED CONTENT")).toBeNull();
    expect(screen.queryByText("LOGIN FORM")).toBeNull();
  });

  it("renders protected content only once authenticated", () => {
    auth.status = "authenticated";
    renderAt();
    expect(screen.getByText("PROTECTED CONTENT")).toBeInTheDocument();
  });
});
