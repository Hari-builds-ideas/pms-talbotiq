import { setupWorker } from "msw/browser";
import { handlers } from "./handlers";

export const worker = setupWorker(...handlers);

/** Start MSW. Called from main.tsx only when VITE_USE_MOCKS=true. */
export async function startMockWorker() {
  await worker.start({
    onUnhandledRequest: "bypass",
    quiet: true,
  });
}
