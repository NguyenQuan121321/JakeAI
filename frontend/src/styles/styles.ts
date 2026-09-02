// Injected scoped CSS styles for JakeAI (TypeScript)
import { JakeTheme } from '../types';

export function injectStyles(_theme: JakeTheme = 'auto'): void {
  if (typeof document === 'undefined') return;
  if (document.getElementById('jake-ai-styles')) return;

  const styleEl = document.createElement('style');
  styleEl.id = 'jake-ai-styles';
  styleEl.textContent = `
    /* JakeAI Container & Themes */
    #jake-ai-container, .jake-ai-root {
      --jake-primary: #ff9f43;
      --jake-primary-hover: #ee8c2e;
      --jake-primary-light: #fff0df;
      --jake-text: #2d3436;
      --jake-text-muted: #636e72;
      --jake-bg: #ffffff;
      --jake-bg-glass: rgba(255, 255, 255, 0.95);
      --jake-card-border: rgba(0, 0, 0, 0.08);
      --jake-shadow: 0 12px 36px rgba(0, 0, 0, 0.16), 0 4px 12px rgba(0, 0, 0, 0.08);
      --jake-msg-ai-bg: #f5f6fa;
      --jake-msg-ai-text: #2f3640;
      --jake-msg-user-bg: #ff9f43;
      --jake-msg-user-text: #ffffff;
      --jake-code-bg: #282c34;
      --jake-code-text: #abb2bf;
      --jake-input-bg: #f8f9fa;
      --jake-input-border: #dfe6e9;
      --jake-font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      font-family: var(--jake-font);
      font-size: 14px;
      line-height: 1.5;
      box-sizing: border-box;
      -webkit-font-smoothing: antialiased;
    }

    #jake-ai-container.jake-theme-dark,
    .jake-ai-root.jake-theme-dark {
      --jake-primary: #ff9f43;
      --jake-primary-hover: #ffa856;
      --jake-primary-light: #3d2a1a;
      --jake-text: #f5f6fa;
      --jake-text-muted: #a4b0be;
      --jake-bg: #1e222d;
      --jake-bg-glass: rgba(30, 34, 45, 0.95);
      --jake-card-border: rgba(255, 255, 255, 0.1);
      --jake-shadow: 0 16px 40px rgba(0, 0, 0, 0.45);
      --jake-msg-ai-bg: #2a2e3d;
      --jake-msg-ai-text: #f1f2f6;
      --jake-msg-user-bg: #ee8c2e;
      --jake-msg-user-text: #ffffff;
      --jake-code-bg: #14171f;
      --jake-code-text: #e1e2e6;
      --jake-input-bg: #2a2e3d;
      --jake-input-border: #3d4356;
    }

    @media (prefers-color-scheme: dark) {
      #jake-ai-container.jake-theme-auto,
      .jake-ai-root.jake-theme-auto {
        --jake-primary: #ff9f43;
        --jake-primary-hover: #ffa856;
        --jake-primary-light: #3d2a1a;
        --jake-text: #f5f6fa;
        --jake-text-muted: #a4b0be;
        --jake-bg: #1e222d;
        --jake-bg-glass: rgba(30, 34, 45, 0.95);
        --jake-card-border: rgba(255, 255, 255, 0.1);
        --jake-shadow: 0 16px 40px rgba(0, 0, 0, 0.45);
        --jake-msg-ai-bg: #2a2e3d;
        --jake-msg-ai-text: #f1f2f6;
        --jake-msg-user-bg: #ee8c2e;
        --jake-msg-user-text: #ffffff;
        --jake-code-bg: #14171f;
        --jake-code-text: #e1e2e6;
        --jake-input-bg: #2a2e3d;
        --jake-input-border: #3d4356;
      }
    }

    #jake-ai-container *, .jake-ai-root * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    /* Corgi Sprite Element */
    #jake-ai-corgi, .jake-corgi-sprite {
      position: fixed;
      top: 0;
      left: 0;
      z-index: 2147483647;
      width: 32px;
      height: 32px;
      cursor: pointer;
      image-rendering: pixelated;
      image-rendering: crisp-edges;
      user-select: none;
      -webkit-user-select: none;
      -webkit-user-drag: none;
      background-repeat: no-repeat;
      display: block;
      pointer-events: auto;
      transform-origin: center center;
      transform: scale(1.3);
      will-change: left, top;
      transition: filter 0.15s ease, transform 0.15s ease;
      touch-action: none;
    }

    #jake-ai-corgi:hover, .jake-corgi-sprite:hover {
      filter: drop-shadow(0 4px 10px rgba(255, 159, 67, 0.6));
      transform: scale(1.45);
    }

    /* Speech Hint Bubble above Corgi */
    .jake-corgi-hint {
      position: absolute;
      bottom: calc(100% + 8px);
      left: 50%;
      transform: translateX(-50%) translateY(4px);
      background: var(--jake-bg, #ffffff);
      color: var(--jake-text, #2d3436);
      font-size: 11.5px;
      font-weight: 600;
      padding: 4px 10px;
      border-radius: 8px;
      white-space: nowrap;
      pointer-events: none;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
      border: 1px solid var(--jake-card-border, rgba(0,0,0,0.1));
      opacity: 0;
      transition: opacity 0.2s ease, transform 0.2s ease;
      z-index: 2147483641;
    }

    .jake-corgi-hint::after {
      content: '';
      position: absolute;
      top: 100%;
      left: 50%;
      transform: translateX(-50%);
      border-width: 5px;
      border-style: solid;
      border-color: var(--jake-bg, #ffffff) transparent transparent transparent;
    }

    #jake-ai-corgi:hover .jake-corgi-hint,
    .jake-corgi-hint.jake-hint-visible {
      opacity: 1;
      transform: translateX(-50%) translateY(0);
    }

    /* Floating Chat Modal */
    #jake-ai-chat, .jake-chat-window {
      position: fixed;
      z-index: 2147483645;
      width: 380px;
      max-width: calc(100vw - 32px);
      height: 520px;
      max-height: calc(100vh - 64px);
      background: var(--jake-bg-glass);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid var(--jake-card-border);
      border-radius: 18px;
      box-shadow: var(--jake-shadow);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      opacity: 0;
      transform: scale(0.92) translateY(16px);
      pointer-events: none;
      transition: opacity 0.25s cubic-bezier(0.16, 1, 0.3, 1), transform 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    }

    #jake-ai-chat.jake-chat-open, .jake-chat-window.jake-chat-open {
      opacity: 1;
      transform: scale(1) translateY(0);
      pointer-events: auto;
    }

    #jake-ai-chat.jake-chat-minimized, .jake-chat-window.jake-chat-minimized {
      height: 56px !important;
      max-height: 56px !important;
    }

    #jake-ai-chat.jake-chat-minimized #jake-ai-messages,
    #jake-ai-chat.jake-chat-minimized #jake-ai-input-form,
    #jake-ai-chat.jake-chat-minimized .jake-quick-actions,
    .jake-chat-window.jake-chat-minimized .jake-chat-body,
    .jake-chat-window.jake-chat-minimized .jake-chat-footer {
      display: none !important;
    }

    /* Chat Header */
    #jake-ai-header, .jake-chat-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 16px;
      background: var(--jake-bg);
      border-bottom: 1px solid var(--jake-card-border);
      cursor: grab;
      user-select: none;
    }

    #jake-ai-header:active, .jake-chat-header:active {
      cursor: grabbing;
    }

    .jake-header-profile {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .jake-avatar-badge {
      width: 32px;
      height: 32px;
      border-radius: 50%;
      background: var(--jake-primary-light);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 18px;
      position: relative;
    }

    .jake-status-dot {
      position: absolute;
      bottom: 0;
      right: 0;
      width: 9px;
      height: 9px;
      background: #2ed573;
      border: 2px solid var(--jake-bg);
      border-radius: 50%;
    }

    .jake-title-wrap {
      display: flex;
      flex-direction: column;
    }

    .jake-title {
      font-size: 14px;
      font-weight: 700;
      color: var(--jake-text);
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .jake-tagline {
      font-size: 11px;
      color: var(--jake-text-muted);
    }

    .jake-header-actions {
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .jake-btn-icon {
      background: transparent;
      border: none;
      color: var(--jake-text-muted);
      cursor: pointer;
      width: 28px;
      height: 28px;
      border-radius: 6px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 13px;
      transition: background 0.15s, color 0.15s;
    }

    .jake-btn-icon:hover {
      background: var(--jake-msg-ai-bg);
      color: var(--jake-text);
    }

    /* Message List */
    #jake-ai-messages, .jake-chat-messages {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      scroll-behavior: smooth;
    }

    #jake-ai-messages::-webkit-scrollbar, .jake-chat-messages::-webkit-scrollbar {
      width: 6px;
    }

    #jake-ai-messages::-webkit-scrollbar-thumb, .jake-chat-messages::-webkit-scrollbar-thumb {
      background: rgba(0, 0, 0, 0.15);
      border-radius: 3px;
    }

    /* Message Bubbles */
    .jake-msg {
      display: flex;
      flex-direction: column;
      max-width: 86%;
      animation: jakeFadeIn 0.2s ease-out;
    }

    @keyframes jakeFadeIn {
      from { opacity: 0; transform: translateY(6px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .jake-msg-ai {
      align-self: flex-start;
    }

    .jake-msg-user {
      align-self: flex-end;
    }

    .jake-msg-bubble {
      padding: 10px 14px;
      border-radius: 14px;
      font-size: 13.5px;
      line-height: 1.5;
      word-break: break-word;
    }

    .jake-msg-ai .jake-msg-bubble {
      background: var(--jake-msg-ai-bg);
      color: var(--jake-msg-ai-text);
      border-bottom-left-radius: 4px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }

    .jake-msg-user .jake-msg-bubble {
      background: var(--jake-msg-user-bg);
      color: var(--jake-msg-user-text);
      border-bottom-right-radius: 4px;
    }

    .jake-msg-time {
      font-size: 10px;
      color: var(--jake-text-muted);
      margin-top: 3px;
      padding: 0 4px;
    }

    .jake-msg-user .jake-msg-time {
      text-align: right;
    }

    /* Markdown Formatted Elements */
    .jake-msg-bubble p {
      margin-bottom: 6px;
    }
    .jake-msg-bubble p:last-child {
      margin-bottom: 0;
    }
    .jake-msg-bubble code {
      font-family: Consolas, Monaco, "Courier New", monospace;
      font-size: 12px;
      padding: 2px 5px;
      background: rgba(0, 0, 0, 0.08);
      border-radius: 4px;
    }
    .jake-msg-user .jake-msg-bubble code {
      background: rgba(255, 255, 255, 0.2);
    }
    .jake-msg-bubble pre {
      background: var(--jake-code-bg);
      color: var(--jake-code-text);
      padding: 10px;
      border-radius: 8px;
      overflow-x: auto;
      font-size: 12px;
      margin: 8px 0;
      font-family: Consolas, Monaco, "Courier New", monospace;
    }
    .jake-msg-bubble pre code {
      background: transparent;
      padding: 0;
      color: inherit;
    }
    .jake-msg-bubble a {
      color: var(--jake-primary);
      text-decoration: underline;
      font-weight: 500;
    }
    .jake-msg-user .jake-msg-bubble a {
      color: #ffffff;
    }
    .jake-msg-bubble ul, .jake-msg-bubble ol {
      padding-left: 18px;
      margin: 6px 0;
    }

    /* Quick Chips */
    .jake-quick-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 4px;
    }

    .jake-chip {
      background: var(--jake-primary-light);
      color: var(--jake-primary-hover);
      font-size: 11.5px;
      font-weight: 500;
      padding: 5px 10px;
      border-radius: 12px;
      border: 1px solid rgba(255, 159, 67, 0.25);
      cursor: pointer;
      transition: all 0.15s ease;
      white-space: nowrap;
    }

    .jake-chip:hover {
      background: var(--jake-primary);
      color: #ffffff;
      transform: translateY(-1px);
    }

    /* Typing Animation */
    .jake-typing {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 10px 14px;
      background: var(--jake-msg-ai-bg);
      border-radius: 14px;
      border-bottom-left-radius: 4px;
      width: fit-content;
    }

    .jake-typing-dot {
      width: 6px;
      height: 6px;
      background: var(--jake-text-muted);
      border-radius: 50%;
      animation: jakeBounce 1.4s infinite ease-in-out both;
    }

    .jake-typing-dot:nth-child(1) { animation-delay: -0.32s; }
    .jake-typing-dot:nth-child(2) { animation-delay: -0.16s; }
    .jake-typing-dot:nth-child(3) { animation-delay: 0s; }

    @keyframes jakeBounce {
      0%, 80%, 100% { transform: scale(0); opacity: 0.4; }
      40% { transform: scale(1); opacity: 1; }
    }

    /* Input Footer */
    #jake-ai-input-form, .jake-chat-footer {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 12px 16px;
      background: var(--jake-bg);
      border-top: 1px solid var(--jake-card-border);
    }

    #jake-ai-input, .jake-chat-input {
      flex: 1;
      background: var(--jake-input-bg);
      border: 1px solid var(--jake-input-border);
      color: var(--jake-text);
      font-family: inherit;
      font-size: 13.5px;
      padding: 9px 14px;
      border-radius: 20px;
      outline: none;
      transition: border-color 0.15s, box-shadow 0.15s;
    }

    #jake-ai-input:focus, .jake-chat-input:focus {
      border-color: var(--jake-primary);
      box-shadow: 0 0 0 3px rgba(255, 159, 67, 0.2);
    }

    #jake-ai-send, .jake-chat-send {
      width: 36px;
      height: 36px;
      border-radius: 50%;
      background: var(--jake-primary);
      color: #ffffff;
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      transition: background 0.15s, transform 0.15s;
    }

    #jake-ai-send:hover, .jake-chat-send:hover {
      background: var(--jake-primary-hover);
      transform: scale(1.05);
    }

    #jake-ai-send:disabled, .jake-chat-send:disabled {
      background: var(--jake-input-border);
      cursor: not-allowed;
      transform: none;
    }

    #jake-ai-send svg, .jake-chat-send svg {
      width: 16px;
      height: 16px;
      fill: currentColor;
    }

    /* Dog House (Jake's Home) */
    #jake-ai-doghouse, .jake-doghouse {
      position: fixed;
      z-index: 2147483638;
      bottom: 20px;
      right: 20px;
      width: 48px;
      height: 48px;
      cursor: pointer;
      background: transparent;
      border: none;
      padding: 0;
      margin: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      user-select: none;
      -webkit-user-select: none;
      transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), filter 0.2s ease;
      touch-action: none;
    }

    #jake-ai-doghouse:hover, .jake-doghouse:hover {
      transform: scale(1.15) translateY(-3px);
      filter: drop-shadow(0 6px 14px rgba(255, 159, 67, 0.5));
    }

    #jake-ai-doghouse:active, .jake-doghouse:active {
      transform: scale(0.95);
    }

    .jake-doghouse-svg {
      width: 100%;
      height: 100%;
      image-rendering: pixelated;
      image-rendering: crisp-edges;
    }

    .jake-doghouse-img {
      width: 100%;
      height: 100%;
      object-fit: contain;
      image-rendering: pixelated;
    }

    .jake-doghouse-tooltip {
      position: absolute;
      bottom: calc(100% + 6px);
      right: 0;
      background: var(--jake-bg, #1e222d);
      color: var(--jake-text, #f5f6fa);
      font-size: 11px;
      font-weight: 600;
      padding: 3px 8px;
      border-radius: 6px;
      white-space: nowrap;
      pointer-events: none;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
      border: 1px solid var(--jake-card-border, rgba(255, 255, 255, 0.1));
      opacity: 0;
      transform: translateY(4px);
      transition: opacity 0.15s ease, transform 0.15s ease;
    }

    #jake-ai-doghouse:hover .jake-doghouse-tooltip,
    .jake-doghouse:hover .jake-doghouse-tooltip {
      opacity: 1;
      transform: translateY(0);
    }

    @media (max-width: 480px) {
      #jake-ai-chat, .jake-chat-window {
        width: calc(100vw - 20px);
        height: 80vh;
        bottom: 10px !important;
        right: 10px !important;
        left: auto !important;
        top: auto !important;
      }
    }
  `;

  document.head.appendChild(styleEl);
}
