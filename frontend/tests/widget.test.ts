/**
 * JakeAI Widget Unit Test Suite
 * Tests Web Component lifecycle, Shadow DOM encapsulation, host token bridge, and mascot states.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { JakeAI, JakeAIWidget } from "../src/index";
import { MascotController } from "../src/mascot";

describe("JakeAI Embedded Widget & Host Token Bridge", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("should register the jake-ai-widget custom element", () => {
    expect(customElements.get("jake-ai-widget")).toBeDefined();
  });

  it("should mount widget and encapsulate UI inside Shadow DOM", () => {
    const widget = document.createElement("jake-ai-widget") as JakeAIWidget;
    document.body.appendChild(widget);

    const shadowRoot = widget.getShadowRoot();
    expect(shadowRoot).toBeDefined();

    const triggerBtn = shadowRoot.querySelector(".jake-trigger-btn");
    expect(triggerBtn).not.toBeNull();

    const chatWindow = shadowRoot.querySelector(".jake-chat-window");
    expect(chatWindow).not.toBeNull();
    expect(chatWindow?.classList.contains("hidden")).toBe(true);
  });

  it("should toggle open and close state", () => {
    const widget = document.createElement("jake-ai-widget") as JakeAIWidget;
    document.body.appendChild(widget);

    const shadowRoot = widget.getShadowRoot();
    const chatWindow = shadowRoot.querySelector(".jake-chat-window");

    // Open
    widget.open();
    expect(chatWindow?.classList.contains("hidden")).toBe(false);

    // Close
    widget.close();
    expect(chatWindow?.classList.contains("hidden")).toBe(true);

    // Toggle
    widget.toggle();
    expect(chatWindow?.classList.contains("hidden")).toBe(false);
  });

  it("should support host token bridge via JakeAI SDK", () => {
    const widget = JakeAI.init({
      apiUrl: "https://api.jakeai.internal/v1/chat/stream",
      token: "initial-finnapigo-token-123",
      initialOpen: false,
    });

    expect(widget).toBeDefined();
    expect(widget.getToken()).toBe("initial-finnapigo-token-123");

    // Rotate token via JakeAI.setToken
    JakeAI.setToken("rotated-jwt-token-456");
    expect(widget.getToken()).toBe("rotated-jwt-token-456");
  });

  it("should transition Corgi mascot animation states", () => {
    const mascot = new MascotController({ initialState: "idle" });
    expect(mascot.getState()).toBe("idle");
    expect(mascot.getElement().getAttribute("data-state")).toBe("idle");

    // Thinking state
    mascot.setState("thinking");
    expect(mascot.getState()).toBe("thinking");
    expect(mascot.getElement().getAttribute("data-state")).toBe("thinking");
    expect(mascot.getElement().innerHTML).toContain("thought-bubbles");

    // Success state
    mascot.setState("success");
    expect(mascot.getState()).toBe("success");
    expect(mascot.getElement().innerHTML).toContain("sparkles");

    // Alert state
    mascot.setState("alert");
    expect(mascot.getState()).toBe("alert");
    expect(mascot.getElement().innerHTML).toContain("alert-mark");
  });

  it("should manage initial welcome message in message store", () => {
    const widget = document.createElement("jake-ai-widget") as JakeAIWidget;
    document.body.appendChild(widget);

    const messages = widget.getMessages();
    expect(messages.length).toBeGreaterThanOrEqual(1);
    expect(messages[0].role).toBe("assistant");
    expect(messages[0].content).toContain("FinnApiGo");
  });

  it("should handle trigger button and close button DOM events", () => {
    const widget = document.createElement("jake-ai-widget") as JakeAIWidget;
    document.body.appendChild(widget);

    const shadow = widget.getShadowRoot();
    const trigger = shadow.querySelector(".jake-trigger-btn") as HTMLButtonElement;
    const closeBtn = shadow.querySelector(".jake-close-btn") as HTMLButtonElement;
    const chatWindow = shadow.querySelector(".jake-chat-window");

    // Click trigger to open
    trigger.click();
    expect(chatWindow?.classList.contains("hidden")).toBe(false);

    // Click close to hide
    closeBtn.click();
    expect(chatWindow?.classList.contains("hidden")).toBe(true);
  });

  it("should handle form submission and message dispatch", () => {
    const widget = document.createElement("jake-ai-widget") as JakeAIWidget;
    document.body.appendChild(widget);

    const shadow = widget.getShadowRoot();
    const input = shadow.querySelector(".jake-input-field") as HTMLInputElement;
    const form = shadow.querySelector(".jake-input-form") as HTMLFormElement;

    expect(input).not.toBeNull();
    expect(form).not.toBeNull();

    let dispatched = "";
    widget.sendMessage = async (msg: string) => {
      dispatched = msg;
    };

    input.value = "Show my portfolio breakdown";
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    expect(dispatched).toBe("Show my portfolio breakdown");
  });

  it("should configure theme, token, and mascot states", () => {
    const widget = document.createElement("jake-ai-widget") as JakeAIWidget;
    document.body.appendChild(widget);

    widget.configure({ theme: "light", token: "bearer-token-999" });
    expect(widget.getToken()).toBe("bearer-token-999");

    widget.setMascotState("thinking");
    expect(widget.getMascotState()).toBe("thinking");

    widget.setMascotState("idle");
    expect(widget.getMascotState()).toBe("idle");
  });
});

