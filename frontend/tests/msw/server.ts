import { setupServer } from "msw/node";
import { handlers } from "./handlers";

/** One MSW server for the whole suite; per-test overrides use server.use(). */
export const server = setupServer(...handlers);
