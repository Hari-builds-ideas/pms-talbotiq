/**
 * AGENT_INTEL_V2 §6 — the chat input UX.
 *  - Enter submits, Shift+Enter inserts a newline (never submits).
 *  - "New chat" clears the thread AND drops the session id, so the next message
 *    starts a fresh server session (no prior memory carried over).
 * No live calls — the chat + session endpoints are mocked.
 */
import * as React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, it, expect, vi } from "vitest";

const chat = vi.fn();
const getSession = vi.fn();
vi.mock("@/lib/api/endpoints", () => ({
  aiApi: {
    chat: (...a: unknown[]) => chat(...a),
    getSession: (...a: unknown[]) => getSession(...a),
  },
}));
vi.mock("@/lib/auth/AuthContext", () => ({
  useAuth: () => ({ me: { id: "u-1", role: "MANAGER" }, hasFeature: () => true }),
}));

import { ChatProvider, useChatPanel } from "./ChatPanel";

// jsdom doesn't implement Element.scrollTo (used by the panel's auto-scroll effect).
Element.prototype.scrollTo = Element.prototype.scrollTo || (() => {});

beforeEach(() => {
  chat.mockReset();
  getSession.mockReset();
  chat.mockResolvedValue({ answer: "ok", status: "ok", session_id: "s-1" });
  localStorage.clear();
});

/** Opens the panel on mount so its input is in the DOM. */
function Opener() {
  const { setOpen } = useChatPanel();
  React.useEffect(() => setOpen(true), [setOpen]);
  return null;
}

function renderPanel() {
  const qc = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ChatProvider>
          <Opener />
        </ChatProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ChatPanel input UX (§6)", () => {
  it("Enter submits the message", async () => {
    const user = userEvent.setup();
    renderPanel();
    const box = await screen.findByLabelText("Chat message");
    await user.type(box, "how is Aarav?");
    await user.keyboard("{Enter}");
    await waitFor(() => expect(chat).toHaveBeenCalledWith("how is Aarav?", undefined));
  });

  it("Shift+Enter inserts a newline and does NOT submit", async () => {
    const user = userEvent.setup();
    renderPanel();
    const box = (await screen.findByLabelText("Chat message")) as HTMLTextAreaElement;
    await user.type(box, "line one");
    await user.keyboard("{Shift>}{Enter}{/Shift}");
    await user.type(box, "line two");
    expect(chat).not.toHaveBeenCalled();
    expect(box.value).toContain("\n");
  });

  it("New chat clears the thread and drops the session id", async () => {
    const user = userEvent.setup();
    renderPanel();
    const box = await screen.findByLabelText("Chat message");
    await user.type(box, "how is Aarav?");
    await user.keyboard("{Enter}");
    await waitFor(() => expect(chat).toHaveBeenCalledTimes(1));
    // the reply grounded a session id that would normally thread into the next turn
    await screen.findByText("ok");

    await user.click(screen.getByRole("button", { name: /start a new chat/i }));
    await waitFor(() => expect(screen.queryByText("ok")).toBeNull()); // thread cleared

    const box2 = await screen.findByLabelText("Chat message");
    await user.type(box2, "does he need help?");
    await user.keyboard("{Enter}");
    // fresh session: the follow-up is sent with NO session id (undefined), so the
    // backend starts a new thread with no memory of the previous person.
    await waitFor(() =>
      expect(chat).toHaveBeenLastCalledWith("does he need help?", undefined),
    );
  });
});
