/**
 * JakeAI Embedded AI Companion Web Component (<jake-ai-widget>)
 * Encapsulated Shadow DOM, SSE streaming consumer, and Corgi mascot companion.
 */

import { MascotController, MascotState } from "./mascot";

export interface JakeAIConfig {
  apiUrl?: string;
  token?: string;
  tenantId?: string;
  theme?: "dark" | "light";
  initialOpen?: boolean;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  toolCalls?: Array<{ name: string; status: "running" | "completed" | "error" }>;
}

export class JakeAIWidget extends HTMLElement {
  private shadow: ShadowRoot;
  private config: JakeAIConfig = {
    apiUrl: "/api/v1/chat/stream",
    token: "",
    theme: "dark",
    initialOpen: false,
  };

  private isOpen = false;
  private isStreaming = false;
  private messages: ChatMessage[] = [];
  private mascot: MascotController;

  // DOM elements inside Shadow DOM
  private windowEl!: HTMLElement;
  private messagesEl!: HTMLElement;
  private inputEl!: HTMLInputElement;
  private sendBtn!: HTMLButtonElement;
  private triggerBtn!: HTMLButtonElement;
  private mascotContainer!: HTMLElement;

  constructor() {
    super();
    this.shadow = this.attachShadow({ mode: "open" });
    this.mascot = new MascotController({ size: 36, initialState: "idle" });
  }

  public connectedCallback(): void {
    this.render();
    this.bindEvents();

    if (this.config.initialOpen) {
      this.open();
    }
  }

  public getShadowRoot(): ShadowRoot {
    return this.shadow;
  }

  public configure(config: JakeAIConfig): void {
    this.config = { ...this.config, ...config };
    if (config.token) {
      this.setToken(config.token);
    }
  }

  public setToken(token: string): void {
    this.config.token = token;
  }

  public getToken(): string | undefined {
    return this.config.token;
  }

  public open(): void {
    this.isOpen = true;
    this.windowEl?.classList.remove("hidden");
    this.inputEl?.focus();
  }

  public close(): void {
    this.isOpen = false;
    this.windowEl?.classList.add("hidden");
  }

  public toggle(): void {
    if (this.isOpen) {
      this.close();
    } else {
      this.open();
    }
  }

  public getMascotState(): MascotState {
    return this.mascot.getState();
  }

  public setMascotState(state: MascotState): void {
    this.mascot.setState(state);
  }

  public getMessages(): ChatMessage[] {
    return [...this.messages];
  }

  public async sendMessage(content: string): Promise<void> {
    const trimmed = content.trim();
    if (!trimmed || this.isStreaming) return;

    // Append user message
    const userMsg: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: "user",
      content: trimmed,
    };
    this.messages.push(userMsg);
    this.appendMessageElement(userMsg);

    if (this.inputEl) {
      this.inputEl.value = "";
    }

    // Prepare assistant message
    const assistantMsg: ChatMessage = {
      id: `msg-resp-${Date.now()}`,
      role: "assistant",
      content: "",
      toolCalls: [],
    };
    this.messages.push(assistantMsg);
    const assistantBubble = this.appendMessageElement(assistantMsg, true);

    await this.streamAssistantResponse(trimmed, assistantMsg, assistantBubble);
  }

  private async streamAssistantResponse(
    query: string,
    assistantMsg: ChatMessage,
    bubbleEl: HTMLElement
  ): Promise<void> {
    this.isStreaming = true;
    this.sendBtn.disabled = true;
    this.mascot.setState("thinking");

    const contentEl = bubbleEl.querySelector(".jake-msg-text") as HTMLElement;
    const toolsContainer = bubbleEl.querySelector(".jake-msg-tools") as HTMLElement;
    const cursor = bubbleEl.querySelector(".jake-cursor") as HTMLElement;

    try {
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (this.config.token) {
        headers["Authorization"] = `Bearer ${this.config.token}`;
      }

      const response = await fetch(this.config.apiUrl || "/api/v1/chat/stream", {
        method: "POST",
        headers,
        body: JSON.stringify({ query }),
      });

      if (!response.ok) {
        throw new Error(`Server returned HTTP ${response.status}: ${response.statusText}`);
      }

      if (!response.body) {
        throw new Error("Response body is not readable");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        let currentEvent = "";
        for (const line of lines) {
          const trimmedLine = line.trim();
          if (trimmedLine.startsWith("event:")) {
            currentEvent = trimmedLine.replace("event:", "").trim();
          } else if (trimmedLine.startsWith("data:")) {
            const dataStr = trimmedLine.replace("data:", "").trim();
            this.handleSSEData(currentEvent, dataStr, assistantMsg, contentEl, toolsContainer);
          }
        }
      }

      // Finish streaming
      cursor?.remove();
      this.mascot.setState("success");
      setTimeout(() => {
        if (this.mascot.getState() === "success") {
          this.mascot.setState("idle");
        }
      }, 2500);
    } catch (err: unknown) {
      cursor?.remove();
      this.mascot.setState("alert");
      const errText = err instanceof Error ? err.message : "Unknown error occurred";
      if (contentEl) {
        contentEl.textContent += `\n[Error: ${errText}]`;
      }
      setTimeout(() => {
        if (this.mascot.getState() === "alert") {
          this.mascot.setState("idle");
        }
      }, 3500);
    } finally {
      this.isStreaming = false;
      this.sendBtn.disabled = false;
    }
  }

  private handleSSEData(
    event: string,
    dataStr: string,
    assistantMsg: ChatMessage,
    contentEl: HTMLElement,
    toolsContainer: HTMLElement
  ): void {
    if (event === "token") {
      try {
        const parsed = JSON.parse(dataStr);
        const token = parsed.token || parsed.content || dataStr;
        assistantMsg.content += token;
        if (contentEl) contentEl.textContent = assistantMsg.content;
      } catch {
        assistantMsg.content += dataStr;
        if (contentEl) contentEl.textContent = assistantMsg.content;
      }
      this.scrollToBottom();
    } else if (event === "tool_call") {
      this.mascot.setState("running");
      try {
        const parsed = JSON.parse(dataStr);
        const toolName = String(parsed.name || parsed.tool || "FinnApiGo");
        const card = document.createElement("div");
        card.className = "jake-tool-card executing";

        const spinner = document.createElement("span");
        spinner.className = "jake-spinner";

        const label = document.createElement("span");
        label.textContent = "Querying ";
        const strong = document.createElement("strong");
        strong.textContent = toolName;
        label.appendChild(strong);
        label.appendChild(document.createTextNode("..."));

        card.appendChild(spinner);
        card.appendChild(label);
        toolsContainer.appendChild(card);
      } catch {
        // Fallback for non-json tool call
      }
      this.scrollToBottom();
    } else if (event === "tool_result") {
      const executingCard = toolsContainer.querySelector(".jake-tool-card.executing");
      if (executingCard) {
        executingCard.className = "jake-tool-card done";
        executingCard.innerHTML = `<span>✓</span> <span>Operation verified</span>`;
      }
      this.mascot.setState("thinking");
      this.scrollToBottom();
    } else if (event === "error") {
      this.mascot.setState("alert");
      try {
        const parsed = JSON.parse(dataStr);
        const errDetail = parsed.error || parsed.detail || "An unexpected error occurred.";
        if (contentEl) {
          contentEl.textContent += `\n[Error: ${errDetail}]`;
        }
      } catch {
        if (contentEl) contentEl.textContent += `\n[Error: ${dataStr}]`;
      }
      this.scrollToBottom();
    } else if (event === "done") {
      // Completed
    }
  }

  private appendMessageElement(msg: ChatMessage, withCursor = false): HTMLElement {
    const msgEl = document.createElement("div");
    msgEl.className = `jake-message ${msg.role}`;
    msgEl.setAttribute("data-id", msg.id);

    const bubble = document.createElement("div");
    bubble.className = "jake-message-bubble";

    const textSpan = document.createElement("span");
    textSpan.className = "jake-msg-text";
    textSpan.textContent = msg.content;
    bubble.appendChild(textSpan);

    if (withCursor) {
      const cursor = document.createElement("span");
      cursor.className = "jake-cursor";
      bubble.appendChild(cursor);
    }

    const toolsSpan = document.createElement("div");
    toolsSpan.className = "jake-msg-tools";
    bubble.appendChild(toolsSpan);

    msgEl.appendChild(bubble);
    this.messagesEl.appendChild(msgEl);
    this.scrollToBottom();
    return msgEl;
  }

  private scrollToBottom(): void {
    if (this.messagesEl) {
      this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
    }
  }

  private render(): void {
    this.shadow.innerHTML = `
      <style>
        :host {
          --jake-primary: #3b82f6;
          --jake-primary-hover: #2563eb;
          --jake-bg-dark: #0f172a;
          --jake-surface: #1e293b;
          --jake-surface-card: #273549;
          --jake-border: #334155;
          --jake-text-primary: #f8fafc;
          --jake-text-secondary: #94a3b8;
          --jake-accent: #f59e0b;
          --jake-success: #10b981;
          --jake-error: #ef4444;
          --jake-radius: 16px;
          --jake-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.5);
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          font-size: 14px;
          color: var(--jake-text-primary);
          line-height: 1.5;
          box-sizing: border-box;
          z-index: 99999;
        }

        *, *::before, *::after { box-sizing: inherit; }

        .jake-trigger-btn {
          position: fixed;
          bottom: 24px;
          right: 24px;
          width: 60px;
          height: 60px;
          border-radius: 50%;
          background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
          border: 2px solid #38bdf8;
          box-shadow: 0 10px 20px rgba(56, 189, 248, 0.3), var(--jake-shadow);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
          z-index: 100000;
          outline: none;
          padding: 0;
        }
        .jake-trigger-btn:hover { transform: scale(1.08) translateY(-2px); }

        .jake-chat-window {
          position: fixed;
          bottom: 96px;
          right: 24px;
          width: 400px;
          max-width: calc(100vw - 48px);
          height: 580px;
          max-height: calc(100vh - 120px);
          background: rgba(15, 23, 42, 0.95);
          backdrop-filter: blur(16px);
          -webkit-backdrop-filter: blur(16px);
          border: 1px solid var(--jake-border);
          border-radius: var(--jake-radius);
          box-shadow: var(--jake-shadow);
          display: flex;
          flex-direction: column;
          overflow: hidden;
          transition: opacity 0.25s ease, transform 0.25s ease;
          z-index: 100000;
        }
        .jake-chat-window.hidden {
          opacity: 0;
          transform: scale(0.9) translateY(20px);
          pointer-events: none;
        }

        .jake-chat-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 14px 18px;
          background: var(--jake-surface);
          border-bottom: 1px solid var(--jake-border);
        }
        .jake-header-left { display: flex; align-items: center; gap: 12px; }
        .jake-header-title h3 {
          margin: 0;
          font-size: 15px;
          font-weight: 600;
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .jake-status-badge {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: var(--jake-success);
          box-shadow: 0 0 8px var(--jake-success);
        }
        .jake-header-subtitle { font-size: 11px; color: var(--jake-text-secondary); }
        .jake-close-btn {
          background: transparent;
          border: none;
          color: var(--jake-text-secondary);
          font-size: 18px;
          cursor: pointer;
          padding: 4px 8px;
          border-radius: 6px;
        }
        .jake-close-btn:hover { color: #fff; background: var(--jake-surface-card); }

        .jake-messages-container {
          flex: 1;
          overflow-y: auto;
          padding: 16px;
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .jake-message { display: flex; flex-direction: column; max-width: 85%; }
        .jake-message.user { align-self: flex-end; }
        .jake-message.assistant { align-self: flex-start; }
        .jake-message-bubble {
          padding: 10px 14px;
          border-radius: 12px;
          word-break: break-word;
          font-size: 13.5px;
          line-height: 1.5;
        }
        .jake-message.user .jake-message-bubble {
          background: var(--jake-primary);
          color: #fff;
          border-bottom-right-radius: 3px;
        }
        .jake-message.assistant .jake-message-bubble {
          background: var(--jake-surface-card);
          color: var(--jake-text-primary);
          border: 1px solid var(--jake-border);
          border-bottom-left-radius: 3px;
        }

        .jake-tool-card {
          margin-top: 6px;
          padding: 6px 10px;
          background: rgba(30, 41, 59, 0.8);
          border: 1px dashed var(--jake-border);
          border-radius: 6px;
          font-size: 11.5px;
          color: var(--jake-text-secondary);
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .jake-tool-card.executing { border-color: #38bdf8; color: #7dd3fc; }
        .jake-tool-card.done { border-color: var(--jake-success); color: #6ee7b7; }
        .jake-spinner {
          width: 10px;
          height: 10px;
          border: 2px solid transparent;
          border-top-color: currentColor;
          border-radius: 50%;
          animation: jakeSpin 0.75s linear infinite;
        }

        .jake-cursor {
          display: inline-block;
          width: 6px;
          height: 14px;
          background: var(--jake-primary);
          margin-left: 3px;
          vertical-align: middle;
          animation: jakeBlink 0.9s infinite;
        }

        .jake-chat-footer {
          padding: 12px 16px;
          background: var(--jake-surface);
          border-top: 1px solid var(--jake-border);
        }
        .jake-input-form { display: flex; gap: 8px; align-items: center; }
        .jake-input-field {
          flex: 1;
          background: var(--jake-bg-dark);
          border: 1px solid var(--jake-border);
          border-radius: 20px;
          padding: 9px 14px;
          color: #fff;
          font-size: 13.5px;
          outline: none;
        }
        .jake-input-field:focus { border-color: var(--jake-primary); }
        .jake-send-btn {
          width: 36px;
          height: 36px;
          border-radius: 50%;
          background: var(--jake-primary);
          color: #fff;
          border: none;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .jake-send-btn:hover:not(:disabled) { background: var(--jake-primary-hover); }
        .jake-footer-note {
          margin-top: 4px;
          text-align: center;
          font-size: 10px;
          color: var(--jake-text-secondary);
        }

        @keyframes jakeBlink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
        @keyframes jakeSpin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
      </style>

      <div class="jake-widget-container">
        <!-- Floating Launcher Button with Mascot -->
        <button class="jake-trigger-btn" aria-label="Open JakeAI Assistant">
          <div class="jake-trigger-mascot"></div>
        </button>

        <!-- Chat Window -->
        <div class="jake-chat-window hidden" role="dialog" aria-label="JakeAI Conversation">
          <header class="jake-chat-header">
            <div class="jake-header-left">
              <div class="jake-header-mascot"></div>
              <div class="jake-header-title">
                <h3>JakeAI <span class="jake-status-badge"></span></h3>
                <span class="jake-header-subtitle">Enterprise Embedded AI Companion</span>
              </div>
            </div>
            <button class="jake-close-btn" aria-label="Close Chat">✕</button>
          </header>

          <div class="jake-messages-container">
            <div class="jake-message assistant">
              <div class="jake-message-bubble">
                <span class="jake-msg-text">Hello! I am Jake, your enterprise financial assistant powered by FinnApiGo. How can I help you today?</span>
              </div>
            </div>
          </div>

          <footer class="jake-chat-footer">
            <form class="jake-input-form">
              <input type="text" class="jake-input-field" placeholder="Ask Jake anything about accounts, audits, or policies..." />
              <button type="submit" class="jake-send-btn" aria-label="Send Message">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                </svg>
              </button>
            </form>
            <div class="jake-footer-note">End-to-end verified via FinnApiGo PEP & LangGraph</div>
          </footer>
        </div>
      </div>
    `;

    // Cache elements
    this.windowEl = this.shadow.querySelector(".jake-chat-window") as HTMLElement;
    this.messagesEl = this.shadow.querySelector(".jake-messages-container") as HTMLElement;
    this.inputEl = this.shadow.querySelector(".jake-input-field") as HTMLInputElement;
    this.sendBtn = this.shadow.querySelector(".jake-send-btn") as HTMLButtonElement;
    this.triggerBtn = this.shadow.querySelector(".jake-trigger-btn") as HTMLButtonElement;

    // Attach mascot to trigger button and header
    const triggerMascotSlot = this.shadow.querySelector(".jake-trigger-mascot") as HTMLElement;
    this.mascotContainer = this.mascot.getElement();
    triggerMascotSlot.appendChild(this.mascotContainer);

    // Initial greeting message
    this.messages.push({
      id: "msg-welcome",
      role: "assistant",
      content: "Hello! I am Jake, your enterprise financial assistant powered by FinnApiGo. How can I help you today?",
    });
  }

  private bindEvents(): void {
    this.triggerBtn?.addEventListener("click", () => this.toggle());

    const closeBtn = this.shadow.querySelector(".jake-close-btn");
    closeBtn?.addEventListener("click", () => this.close());

    const form = this.shadow.querySelector(".jake-input-form");
    form?.addEventListener("submit", (e) => {
      e.preventDefault();
      if (this.inputEl) {
        this.sendMessage(this.inputEl.value);
      }
    });
  }
}
