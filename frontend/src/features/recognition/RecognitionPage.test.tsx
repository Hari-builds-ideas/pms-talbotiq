/**
 * RW_BUILD_2 2.3 — the recognition feed renders cards with their parties, value and
 * message, surfaces each card's VISIBILITY (so the viewer knows who can see it), and
 * invites the first recognition when empty. (Server enforces who receives which card;
 * this asserts the client renders what it's given correctly.)
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

const CARDS = [
  {
    id: "r1",
    sender: { id: "s1", display: "Sam Sender" },
    recipient: { id: "a1", display: "Ada Recipient" },
    value: "Teamwork",
    message: "Great pairing on the launch",
    badge: "",
    visibility: "COMPANY",
    created_at: "2026-06-27T00:00:00Z",
    reactions: { counts: { "👍": 2 }, mine: [] },
    can_delete: false,
  },
  {
    id: "r2",
    sender: { id: "s1", display: "Sam Sender" },
    recipient: { id: "a1", display: "Ada Recipient" },
    value: "Ownership",
    message: "Owned the incident end to end",
    badge: "",
    visibility: "PRIVATE",
    created_at: "2026-06-27T00:00:00Z",
    reactions: { counts: {}, mine: [] },
    can_delete: true,
  },
];

const feed = vi.hoisted(() => ({ data: [] as unknown[], isLoading: false, isError: false, refetch: () => {} }));

vi.mock("./useRecognition", () => ({
  useRecognitionFeed: () => feed,
  useRecognitionMeta: () => ({
    data: { reactions: ["👍", "❤️"], values: ["Teamwork", "Ownership"], visibilities: [{ value: "TEAM", label: "Team" }] },
  }),
  useRecognitionMutations: () => ({
    give: { mutateAsync: vi.fn(), isPending: false },
    react: { mutateAsync: vi.fn(() => Promise.resolve()) },
    remove: { mutateAsync: vi.fn(() => Promise.resolve()), isPending: false },
  }),
}));
vi.mock("@/lib/auth/AuthContext", () => ({ useAuth: () => ({ me: { id: "viewer" } }) }));
vi.mock("@/lib/hooks/useDirectory", () => ({ useDirectory: () => ({ nodes: {} }) }));

import { RecognitionPage } from "./RecognitionPage";

describe("RecognitionPage", () => {
  it("invites the first recognition when the feed is empty", () => {
    feed.data = [];
    render(<RecognitionPage />);
    expect(screen.getByText(/No recognitions yet/i)).toBeInTheDocument();
  });

  it("renders feed cards with parties, value and message", () => {
    feed.data = CARDS;
    render(<RecognitionPage />);
    expect(screen.getAllByText("Sam Sender").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Ada Recipient").length).toBeGreaterThan(0);
    expect(screen.getByText("Great pairing on the launch")).toBeInTheDocument();
    expect(screen.getByText("Teamwork")).toBeInTheDocument();
  });

  it("surfaces each card's visibility (who can see it)", () => {
    feed.data = CARDS;
    render(<RecognitionPage />);
    expect(screen.getByText("Company")).toBeInTheDocument(); // the COMPANY card
    expect(screen.getByText("Private")).toBeInTheDocument(); // the PRIVATE card
  });
});
