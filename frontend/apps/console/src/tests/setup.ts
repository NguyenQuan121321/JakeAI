import "@testing-library/jest-dom";

// Mock matchMedia for happy-dom/jsdom
Object.defineProperty(window, "matchMedia", {
  writable: true,
  configurable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

import { beforeAll, afterEach, afterAll } from "vitest";
import { server } from "../mocks/server";

beforeAll(() => {
  if (typeof window !== "undefined") {
    window.fetch = (input: RequestInfo | URL, init?: RequestInit) => globalThis.fetch(input, init);
  }
  server.listen({ onUnhandledRequest: "bypass" });
});
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

