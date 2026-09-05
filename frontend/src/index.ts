/**
 * JakeAI Embedded Client Library & Widget SDK
 * Dual-mode distribution: ESM and UMD bundle with Shadow DOM encapsulation.
 */

import "./style.css";
import { JakeAIWidget } from "./widget";
import type { JakeAIConfig } from "./widget";
import { MascotController } from "./mascot";
import type { MascotState } from "./mascot";

export { JakeAIWidget, MascotController };
export type { JakeAIConfig, MascotState };

// Register custom element if not already registered in window
if (typeof window !== "undefined" && typeof customElements !== "undefined") {
  if (!customElements.get("jake-ai-widget")) {
    customElements.define("jake-ai-widget", JakeAIWidget);
  }
}

let activeInstance: JakeAIWidget | null = null;

export const JakeAI = {
  /**
   * Initializes and injects the JakeAI widget into the host DOM.
   */
  init(config: JakeAIConfig = {}): JakeAIWidget {
    if (typeof document === "undefined") {
      throw new Error("JakeAI.init() must be executed in a browser DOM environment.");
    }

    let widget = document.querySelector("jake-ai-widget") as JakeAIWidget | null;
    if (!widget) {
      widget = document.createElement("jake-ai-widget") as JakeAIWidget;
      document.body.appendChild(widget);
    }

    widget.configure(config);
    activeInstance = widget;
    return widget;
  },

  /**
   * Host Token Bridge: sets or rotates the FinnApiGo Bearer JWT token.
   */
  setToken(token: string): void {
    if (activeInstance) {
      activeInstance.setToken(token);
    } else if (typeof document !== "undefined") {
      const widget = document.querySelector("jake-ai-widget") as JakeAIWidget | null;
      if (widget) {
        widget.setToken(token);
        activeInstance = widget;
      }
    }
  },

  /**
   * Opens the chat interface.
   */
  open(): void {
    activeInstance?.open();
  },

  /**
   * Closes the chat interface.
   */
  close(): void {
    activeInstance?.close();
  },

  /**
   * Toggles the chat interface.
   */
  toggle(): void {
    activeInstance?.toggle();
  },

  /**
   * Returns the active JakeAIWidget DOM node.
   */
  getWidget(): JakeAIWidget | null {
    return activeInstance;
  },
};

// Expose on global window object for script tag consumers
if (typeof window !== "undefined") {
  (window as unknown as { JakeAI: typeof JakeAI }).JakeAI = JakeAI;
}

export default JakeAI;
