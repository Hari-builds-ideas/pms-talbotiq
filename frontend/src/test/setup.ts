import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import { configureWebApiClient } from "@/lib/api/configure";

// jsdom lacks a few browser APIs that Radix/cmdk use (they exist in every real
// browser). Stub them so rendering overlay widgets — dialogs, the cmdk palette —
// doesn't crash the a11y suite. No effect on the app at runtime.
if (!("ResizeObserver" in globalThis)) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}
if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// Wire the shared API client (token store + base URL) for tests, exactly as the
// app does at bootstrap — so behaviour matches the pre-extraction client.
configureWebApiClient();

// Tear down the rendered DOM between tests.
afterEach(() => cleanup());
