import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import { configureWebApiClient } from "@/lib/api/configure";

// Wire the shared API client (token store + base URL) for tests, exactly as the
// app does at bootstrap — so behaviour matches the pre-extraction client.
configureWebApiClient();

// Tear down the rendered DOM between tests.
afterEach(() => cleanup());
