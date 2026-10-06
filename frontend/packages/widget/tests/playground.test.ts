import { beforeEach, expect, it, vi } from "vitest";

const { configure, init } = vi.hoisted(() => {
  const configure = vi.fn();
  return { configure, init: vi.fn(() => ({ configure })) };
});
vi.mock("../src/index", () => ({ JakeAI: { init, open: vi.fn() } }));

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  document.body.innerHTML = `
    <input id="jwt-token"><input id="backend-url" value="http://localhost:8000/api/v1/chat/stream">
    <button id="update-token-btn"></button><button id="open-widget-btn"></button>
    <button id="save-byok-btn"></button><input id="byok-key" value="synthetic">
    <select id="byok-provider"><option>openai</option></select><div id="byok-status"></div>`;
  vi.stubGlobal("alert", vi.fn());
  vi.stubGlobal("fetch", vi.fn());
});

it("starts without credentials and applies the user's login token", async () => {
  await import("../src/playground");
  expect(init).toHaveBeenCalledWith(expect.objectContaining({ token: "" }));
  const input = document.getElementById("jwt-token") as HTMLInputElement;
  expect(input.value).toBe("");
  input.value = "user-supplied-access-token";
  document.getElementById("update-token-btn")!.click();
  expect(configure).toHaveBeenCalledWith({
    apiUrl: "http://localhost:8000/api/v1/chat/stream",
    token: "user-supplied-access-token",
  });
});

it("does not register a BYOK key before the user supplies authentication", async () => {
  await import("../src/playground");
  document.getElementById("save-byok-btn")!.click();
  expect(fetch).not.toHaveBeenCalled();
  expect(document.getElementById("byok-status")!.textContent).toContain("Sign in");
});
