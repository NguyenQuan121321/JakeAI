/**
 * JakeAI Corgi Mascot Animation Controller
 * Manages the animated Corgi companion states (idle, running, thinking, success, alert)
 * rendered using an encapsulated SVG vector engine.
 */

export type MascotState = "idle" | "running" | "thinking" | "success" | "alert";

export interface MascotOptions {
  size?: number;
  initialState?: MascotState;
}

export class MascotController {
  private state: MascotState;
  private container: HTMLElement;
  private size: number;

  constructor(options: MascotOptions = {}) {
    this.state = options.initialState || "idle";
    this.size = options.size || 48;
    this.container = document.createElement("div");
    this.container.className = "jake-mascot-wrapper";
    this.container.setAttribute("data-state", this.state);
    this.render();
  }

  public getState(): MascotState {
    return this.state;
  }

  public setState(newState: MascotState): void {
    if (this.state === newState) return;
    this.state = newState;
    this.container.setAttribute("data-state", newState);
    this.render();
  }

  public getElement(): HTMLElement {
    return this.container;
  }

  public attachTo(parent: HTMLElement): void {
    parent.appendChild(this.container);
  }

  private render(): void {
    this.container.innerHTML = this.generateSVG();
  }

  private generateSVG(): string {
    const s = this.size;
    let badge = "";
    let eyeLeft = `<circle cx="16" cy="22" r="2.5" fill="#2d3748" />`;
    let eyeRight = `<circle cx="32" cy="22" r="2.5" fill="#2d3748" />`;
    let mouth = `<path d="M 21 28 Q 24 30 27 28" stroke="#2d3748" stroke-width="1.8" fill="none" stroke-linecap="round" />`;
    let animationClass = "state-idle";

    switch (this.state) {
      case "thinking":
        animationClass = "state-thinking";
        eyeLeft = `<circle cx="16" cy="20" r="2" fill="#2d3748" /><circle cx="16" cy="18" r="0.8" fill="#fff" />`;
        eyeRight = `<circle cx="32" cy="20" r="2" fill="#2d3748" /><circle cx="32" cy="18" r="0.8" fill="#fff" />`;
        badge = `
          <g class="thought-bubbles">
            <circle cx="38" cy="10" r="2" fill="#3b82f6" opacity="0.6" />
            <circle cx="43" cy="6" r="3.5" fill="#60a5fa" opacity="0.8" />
            <circle cx="44" cy="4" r="1.2" fill="#ffffff" />
          </g>
        `;
        mouth = `<circle cx="24" cy="28" r="2" fill="#2d3748" />`;
        break;

      case "success":
        animationClass = "state-success";
        eyeLeft = `<path d="M 13 22 Q 16 19 19 22" stroke="#10b981" stroke-width="2.2" fill="none" stroke-linecap="round" />`;
        eyeRight = `<path d="M 29 22 Q 32 19 35 22" stroke="#10b981" stroke-width="2.2" fill="none" stroke-linecap="round" />`;
        mouth = `<path d="M 20 27 Q 24 33 28 27" fill="#ef4444" stroke="#2d3748" stroke-width="1.5" />`;
        badge = `
          <g class="sparkles">
            <path d="M 40 10 L 41 13 L 44 14 L 41 15 L 40 18 L 39 15 L 36 14 L 39 13 Z" fill="#fbbf24" />
          </g>
        `;
        break;

      case "alert":
        animationClass = "state-alert";
        eyeLeft = `<circle cx="16" cy="22" r="3" fill="#ef4444" /><circle cx="16" cy="22" r="1" fill="#fff" />`;
        eyeRight = `<circle cx="32" cy="22" r="3" fill="#ef4444" /><circle cx="32" cy="22" r="1" fill="#fff" />`;
        mouth = `<path d="M 21 29 Q 24 26 27 29" stroke="#ef4444" stroke-width="2" fill="none" stroke-linecap="round" />`;
        badge = `
          <g class="alert-mark">
            <circle cx="40" cy="8" r="5" fill="#ef4444" />
            <text x="40" y="11" font-size="7" font-weight="bold" fill="#ffffff" text-anchor="middle">!</text>
          </g>
        `;
        break;

      case "running":
        animationClass = "state-running";
        mouth = `<path d="M 20 28 Q 24 32 28 28" stroke="#2d3748" stroke-width="1.8" fill="none" stroke-linecap="round" />`;
        break;

      case "idle":
      default:
        animationClass = "state-idle";
        break;
    }

    return `
      <svg class="jake-corgi-svg ${animationClass}" width="${s}" height="${s}" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="corgiFur" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stop-color="#f6ad55" />
            <stop offset="100%" stop-color="#dd6b20" />
          </linearGradient>
          <linearGradient id="corgiEarInner" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#fed7d7" />
            <stop offset="100%" stop-color="#feb2b2" />
          </linearGradient>
        </defs>

        <!-- Left Ear -->
        <path class="corgi-ear ear-left" d="M 8 18 C 6 8, 14 4, 18 12 Z" fill="url(#corgiFur)" />
        <path d="M 9 16 C 8 10, 13 7, 16 12 Z" fill="url(#corgiEarInner)" />

        <!-- Right Ear -->
        <path class="corgi-ear ear-right" d="M 40 18 C 42 8, 34 4, 30 12 Z" fill="url(#corgiFur)" />
        <path d="M 39 16 C 40 10, 35 7, 32 12 Z" fill="url(#corgiEarInner)" />

        <!-- Head Base -->
        <circle cx="24" cy="25" r="16" fill="url(#corgiFur)" />

        <!-- White Muzzle Patch -->
        <ellipse cx="24" cy="28" rx="8" ry="6.5" fill="#ffffff" />
        <path d="M 22 17 L 26 17 L 25 24 L 23 24 Z" fill="#ffffff" />

        <!-- Nose -->
        <polygon points="22,25 26,25 24,27.5" fill="#2d3748" />

        <!-- Eyes -->
        <g class="corgi-eyes">
          ${eyeLeft}
          ${eyeRight}
        </g>

        <!-- Mouth -->
        ${mouth}

        <!-- Status / Reaction Badge -->
        ${badge}
      </svg>
    `;
  }
}
