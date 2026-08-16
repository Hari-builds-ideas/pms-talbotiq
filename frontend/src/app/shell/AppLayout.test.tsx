/**
 * The shell's sidebar default, per viewport.
 *
 * The sidebar is 256px wide and used to start OPEN at every width. On a 390px phone
 * that left ~130px of content and the dashboard rendered with its stat cards on top
 * of each other — no horizontal overflow, so an automated overflow check passed it;
 * it was only visible in a screenshot.
 */
import { fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

describe("AppLayout sidebar drawer semantics (below md)", () => {
  beforeEach(() => window.localStorage.clear());

  it("announces itself as a modal dialog only while it is a drawer", () => {
    setViewport(false);
    renderShell();
    fireEvent.click(screen.getByLabelText("Toggle navigation"));
    const aside = document.querySelector("aside")!;
    expect(aside.getAttribute("role")).toBe("dialog");
    expect(aside.getAttribute("aria-modal")).toBe("true");
  });

  it("is plain navigation on desktop, not a dialog", () => {
    setViewport(true);
    renderShell();
    const aside = document.querySelector("aside")!;
    expect(aside.getAttribute("role")).toBeNull();
    expect(aside.getAttribute("aria-modal")).toBeNull();
  });

  it("moves focus into the drawer when it opens", () => {
    setViewport(false);
    renderShell();
    fireEvent.click(screen.getByLabelText("Toggle navigation"));
    const aside = document.querySelector("aside")!;
    expect(aside.contains(document.activeElement)).toBe(true);
  });

  it("closes on Escape and returns focus to the toggle", () => {
    setViewport(false);
    renderShell();
    const toggle = screen.getByLabelText("Toggle navigation");
    // Focus explicitly first: a real tap/keyboard activation focuses the button,
    // but jsdom's synthetic click does not, and the restore target is whatever
    // held focus when the drawer opened.
    toggle.focus();
    fireEvent.click(toggle);
    expect(document.querySelector("aside")).not.toBeNull();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(document.querySelector("aside")).toBeNull();
    // Focus must come back to what opened it, or a keyboard user is stranded at
    // the top of the document.
    expect(document.activeElement).toBe(toggle);
  });

  it("reflects open state on the toggle for assistive tech", () => {
    setViewport(false);
    renderShell();
    const toggle = screen.getByLabelText("Toggle navigation");
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
  });

  it("never persists an open drawer into a mobile session", () => {
    setViewport(false);
    renderShell();
    fireEvent.click(screen.getByLabelText("Toggle navigation"));
    // Opening a drawer on a phone is session state, not a preference. Persisting
    // it would put the menu back over the content on the next load.
    expect(window.localStorage.getItem("pms.nav.desktopOpen")).toBeNull();
  });

  it("persists the collapse preference on desktop", () => {
    setViewport(true);
    renderShell();
    fireEvent.click(screen.getByLabelText("Toggle navigation"));
    expect(window.localStorage.getItem("pms.nav.desktopOpen")).toBe("false");
    expect(document.querySelector("aside")).toBeNull();
  });

  it("restores the stored desktop preference on mount", () => {
    window.localStorage.setItem("pms.nav.desktopOpen", "false");
    setViewport(true);
    renderShell();
    expect(document.querySelector("aside")).toBeNull();
  });
});
