import { setupServer } from "msw/node";
import { handlers } from "./handlers";

/** MSW node server for tests — reuses the same handlers as the browser worker so
 * the a11y suite renders the real screens with realistic data. */
export const server = setupServer(...handlers);
