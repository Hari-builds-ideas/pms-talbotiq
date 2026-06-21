import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import axe from "axe-core";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AppLayout } from "@/app/shell/AppLayout";

/** A fresh query client per render — no retries/caching so screens settle fast. */
function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
}

/** Render a screen inside the real authenticated shell (sidebar + topbar + main),
 * at a chosen route, so axe sees landmarks + skip-link + the screen together. */
export function renderInShell(ui: ReactElement, path = "/") {
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path={path} element={ui} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Render a bare screen (no shell) — e.g. the login page. */
export function renderBare(ui: ReactElement, path = "/") {
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const AA_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

/** Run axe over a container at WCAG 2.1 A/AA and return the violations. jsdom has
 * no layout engine, so layout-dependent rules (color-contrast) come back as
 * "incomplete" rather than violations — those are covered by the token-contrast
 * check + the documented manual pass (see docs/ACCESSIBILITY.md). */
export async function axeViolations(container: HTMLElement) {
  const results = await axe.run(container, {
    runOnly: { type: "tag", values: AA_TAGS },
    resultTypes: ["violations"],
  });
  return results.violations;
}

/** A compact one-line-per-violation summary for assertion failure messages. */
export function summarize(violations: Awaited<ReturnType<typeof axeViolations>>) {
  return violations
    .map(
      (v) =>
        `[${v.impact}] ${v.id}: ${v.help} (${v.nodes.length}) — ` +
        v.nodes.slice(0, 2).map((n) => n.target.join(" ")).join(" | "),
    )
    .join("\n");
}
