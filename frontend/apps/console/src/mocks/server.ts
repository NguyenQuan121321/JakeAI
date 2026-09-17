/**
 * MSW Node Server Setup (Used for Vitest Unit & Integration Tests)
 */

import { setupServer } from "msw/node";
import { handlers } from "./handlers";

export const server = setupServer(...handlers);
