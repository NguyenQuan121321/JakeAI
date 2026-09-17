/**
 * MSW Browser Worker Setup (Used for Optional Mock Development Mode)
 */

import { setupWorker } from "msw/browser";
import { handlers } from "./handlers";

export const worker = typeof window !== "undefined" ? setupWorker(...handlers) : null;
