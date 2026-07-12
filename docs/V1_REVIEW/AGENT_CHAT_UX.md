# AGENT_CHAT_UX — persistent, resizable copilot (E1 + E2)

## Architecture found (pre-change)
The chat was already structurally a copilot, not a modal:
- Mounted at **shell level**, outside the route outlet (`ChatProvider` renders `{children}` + `<ChatSheet/>`;
  `AppLayout.tsx`) → **navigation never unmounted it**; `turns` + `session_id` survive route changes.
- Radix Sheet rendered **non-modal, no overlay, outside-click dismissal blocked**
  (`modal={false}`, `overlay={false}`, `onInteractOutside preventDefault` — `ChatPanel.tsx`).

What was missing: a **fixed width** (`sm:max-w-md`, no resize), and the page was **overlaid** rather than
sharing the space, so the panel covered content instead of sitting beside it.

## What was implemented (this run)

### E1 — resizable
- Panel width is state on `ChatProvider` (`width`, `setWidth`), **clamped 320–720px**, **persisted** to
  `localStorage["pms.chat.width"]` and rehydrated on load (`ChatPanel.tsx`).
- A **drag handle** on the panel's left edge (`ResizeHandle`, `role="separator"`,
  `aria-label="Resize chat panel"`): pointer-down tracks `pointermove` → `setWidth(window.innerWidth −
  clientX)`; body cursor set during drag. No new dependencies.
- `SheetContent` takes the width inline (`style={{ width, maxWidth: "100vw" }}`); Tailwind's `transition`
  class does not animate width, so dragging is crisp.

### E2 — persistent, non-blocking, side-by-side
- Already persistent across navigation (above) — verified and kept.
- **Content now shrinks beside the panel:** the shell (`AppLayout.tsx` → new `ShellFrame`) reads
  `open` + `width` from the chat context and applies `margin-right: var(--chat-w)` (≥ `sm`) when the
  panel is open — the page re-flows and the copilot docks beside it, exactly the "AI says go to X page →
  click it → page loads beside the still-open chat" flow. On mobile the panel is full-width and overlays
  (no useful side-by-side there).
- No auto-dismiss on navigation or outside click (unchanged); the panel closes only via its X, the
  Ask-AI toggle, or ESC (an explicit action).

### Session persistence across reload
Handled with the C (agent memory) fix: `session_id` is persisted to `localStorage` and the conversation
is rehydrated from the server session on mount — see `AGENT_MEMORY_REVIEW.md`.

## Files changed
- `frontend/src/features/chat/ChatPanel.tsx` — width state + clamp + persistence, `ResizeHandle`,
  context exposes `width`/`setWidth`, inline panel width.
- `frontend/src/app/shell/AppLayout.tsx` — `ShellFrame` reads chat state; content column gets
  `sm:mr-[var(--chat-w)]` while open.

Verified: `tsc` clean; full vitest suite green after the change.
