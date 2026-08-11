/**
 * The shell's sidebar default, per viewport.
 *
 * The sidebar is 256px wide and used to start OPEN at every width. On a 390px phone
 * that left ~130px of content and the dashboard rendered with its stat cards on top
 * of each other — no horizontal overflow, so an automated overflow check passed it;
 * it was only visible in a screenshot.
 */
import { fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// Reuse the a11y harness: it wraps AppLayout in the QueryClientProvider the
// command palette needs, so this file tests the shell rather than re-scaffolding it.
import { renderInShell } from "@/test/a11y/harness";

// The same shape the a11y suite uses. The shell's children read more than `me` off
// this context, and a partial mock takes them out with "atLeast is not a function".
vi.mock("@/lib/auth/AuthContext", () => ({
  useAuth: () => ({
    me: {
      id: "u1",
      email: "admin@acme.test",
      role: "ADMIN",
      display_name: "Avery",
      tenant_name: "Acme",
      tenant_slug: "acme",
      mfa_enabled: false,
      manager_id: null,
    },
    status: "authenticated",
    features: {},
    hasFeature: () => true,
    atLeast: () => true,
    logout: vi.fn(),
    completeLogin: vi.fn(),
    refreshFeatures: vi.fn(),
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));

/** jsdom implements no matchMedia, so each test installs the one it needs. */
function setViewport(isDesktop: boolean | null) {
  if (isDesktop === null) {
    // @ts-expect-error — deliberately removing it, which is jsdom's real default.
    delete window.matchMedia;
    return;
  }
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: isDesktop,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}

function renderShell() {
  return renderInShell(<div>content</div>, "/");
}

afterEach(() => setViewport(null));

describe("AppLayout sidebar default", () => {
  it("starts CLOSED on a phone viewport", () => {
    setViewport(false);
    renderShell();
    expect(document.querySelector("aside")).toBeNull();
  });

  it("starts OPEN on a desktop viewport", () => {
    setViewport(true);
    renderShell();
    expect(document.querySelector("aside")).not.toBeNull();
  });

  it("offers a way to dismiss the overlaying menu on a phone", () => {
    setViewport(false);
    renderShell();
    // fireEvent, not node.click(): a raw DOM click does not drive React's state
    // update here, so the assertion below would fail against a working component.
    // Exact label — /menu/i also matched the user menu.
    fireEvent.click(screen.getByLabelText("Toggle navigation"));
    expect(screen.getByLabelText(/close navigation/i)).toBeTruthy();
  });

  it("assumes desktop where matchMedia does not exist", () => {
    // SSR and jsdom both lack it. An unguarded call here took out 14 tests at once,
    // so the fallback is asserted rather than left to chance.
    setViewport(null);
    renderShell();
    expect(document.querySelector("aside")).not.toBeNull();
  });
});
