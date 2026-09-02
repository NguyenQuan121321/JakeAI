// Decoupled 60-120 FPS Physics & Movement Controller (TypeScript)
import { SpriteEngine } from './SpriteEngine';
import { DirectionName, JakeProps } from '../types';

export class MovementEngine {
  public element: HTMLElement;
  public spriteEngine: SpriteEngine;
  public config: Required<JakeProps>;

  public corgiX: number = 100;
  public corgiY: number = 100;
  public targetX: number = 100;
  public targetY: number = 100;

  public lastDirection: DirectionName = 'S';
  public frameCount: number = 0;
  public idleTime: number = 0;
  public lastTimestamp: number = 0;
  public isChatOpen: boolean = false;
  public isPaused: boolean = false;

  private onCorgiClick?: (x: number, y: number) => void;
  private tooltipEl?: HTMLElement;
  private hintTimer?: ReturnType<typeof setTimeout>;

  constructor(
    element: HTMLElement,
    props: JakeProps = {},
    onCorgiClick?: (x: number, y: number) => void
  ) {
    this.element = element;
    this.onCorgiClick = onCorgiClick;
    this.config = {
      backendUrl: props.backendUrl || '',
      greeting: props.greeting || "Hi! I'm Jake, your portfolio guide 🐕",
      position: props.position || 'bottom-right',
      speed: props.speed ?? 10,
      theme: props.theme || 'auto',
      name: props.name || 'Jake',
      persistPosition: props.persistPosition ?? true,
      quickChips: props.quickChips || [],
      enableSound: props.enableSound ?? true,
      className: props.className || '',
      style: props.style || {}
    };

    this.spriteEngine = new SpriteEngine(this.element);

    this.initPosition();
    this.setupListeners();
    this.createTooltip();
  }

  private initPosition(): void {
    let saved: { x: number; y: number; dir?: DirectionName } | null = null;
    if (this.config.persistPosition && typeof window !== 'undefined') {
      try {
        const raw = window.localStorage.getItem('jakeai_pos');
        if (raw) saved = JSON.parse(raw);
      } catch {
        // ignore storage errors
      }
    }

    if (saved && typeof saved.x === 'number' && typeof saved.y === 'number') {
      this.corgiX = Math.min(Math.max(20, saved.x), window.innerWidth - 20);
      this.corgiY = Math.min(Math.max(20, saved.y), window.innerHeight - 20);
      this.lastDirection = saved.dir || 'S';
    } else if (typeof window !== 'undefined') {
      const pos = String(this.config.position).toLowerCase();
      const margin = 80;
      switch (pos) {
        case 'bottom-left':
          this.corgiX = margin;
          this.corgiY = window.innerHeight - margin;
          this.lastDirection = 'NE';
          break;
        case 'top-left':
          this.corgiX = margin;
          this.corgiY = margin;
          this.lastDirection = 'SE';
          break;
        case 'top-right':
          this.corgiX = window.innerWidth - margin;
          this.corgiY = margin;
          this.lastDirection = 'SW';
          break;
        case 'center':
          this.corgiX = window.innerWidth / 2;
          this.corgiY = window.innerHeight / 2;
          this.lastDirection = 'S';
          break;
        case 'bottom-right':
        default:
          this.corgiX = window.innerWidth - margin;
          this.corgiY = window.innerHeight - margin;
          this.lastDirection = 'NW';
          break;
      }
    }

    this.targetX = this.corgiX;
    this.targetY = this.corgiY;
    this.updatePosition();
    this.spriteEngine.setSprite('idle', this.lastDirection, 0);
  }

  private setupListeners(): void {
    if (typeof window === 'undefined') return;

    window.addEventListener('mousemove', (e: MouseEvent) => {
      this.targetX = e.clientX;
      this.targetY = e.clientY;
    }, { passive: true });

    window.addEventListener('touchmove', (e: TouchEvent) => {
      if (e.touches && e.touches[0]) {
        this.targetX = e.touches[0].clientX;
        this.targetY = e.touches[0].clientY;
      }
    }, { passive: true });

    this.element.addEventListener('click', (e: MouseEvent) => {
      e.stopPropagation();
      if (this.onCorgiClick) {
        this.onCorgiClick(this.corgiX, this.corgiY);
      }
    });

    if (this.config.persistPosition) {
      window.addEventListener('beforeunload', () => {
        try {
          window.localStorage.setItem('jakeai_pos', JSON.stringify({
            x: Math.round(this.corgiX),
            y: Math.round(this.corgiY),
            dir: this.lastDirection
          }));
        } catch {
          // ignore storage error
        }
      });
    }

    window.addEventListener('resize', () => {
      this.corgiX = Math.min(Math.max(20, this.corgiX), window.innerWidth - 20);
      this.corgiY = Math.min(Math.max(20, this.corgiY), window.innerHeight - 20);
      this.updatePosition();
    });
  }

  private createTooltip(): void {
    if (typeof document === 'undefined') return;
    const hint = document.createElement('div');
    hint.className = 'jake-corgi-hint';
    hint.textContent = 'Click to chat! 🐕';
    this.element.appendChild(hint);
    this.tooltipEl = hint;
  }

  public showHint(text: string = 'Woof! 🐾', durationMs: number = 3000): void {
    if (!this.tooltipEl) return;
    this.tooltipEl.textContent = text;
    this.tooltipEl.classList.add('jake-hint-visible');
    if (this.hintTimer) clearTimeout(this.hintTimer);
    this.hintTimer = setTimeout(() => {
      this.tooltipEl?.classList.remove('jake-hint-visible');
    }, durationMs);
  }

  public updatePosition(): void {
    const size = this.spriteEngine.currentState === 'running' ? 37 : 32;
    const half = size / 2;
    const posX = Math.round(this.corgiX - half);
    const posY = Math.round(this.corgiY - half);

    this.element.style.left = `${posX}px`;
    this.element.style.top = `${posY}px`;
  }

  public step(timestamp: number): void {
    if (!this.element.isConnected) return;

    if (!this.lastTimestamp) this.lastTimestamp = timestamp;
    const elapsed = timestamp - this.lastTimestamp;

    // 80ms cadence for sprite frame steps (~12.5 FPS sprite walk cycle)
    if (elapsed >= 80) {
      this.lastTimestamp = timestamp;
      this.tick();
    }
  }

  public tick(): void {
    if (this.isPaused) return;

    const dx = this.targetX - this.corgiX;
    const dy = this.targetY - this.corgiY;
    const distance = Math.hypot(dx, dy);

    // Stop distance threshold
    const stopDistance = 48;
    if (distance <= stopDistance) {
      this.idleTime += 1;
      this.frameCount = 0;

      if (distance > 10) {
        const dir = SpriteEngine.getDirection(dx, dy);
        this.lastDirection = dir.name;
      }

      this.spriteEngine.setSprite('idle', this.lastDirection, 0);
      this.updatePosition();
      return;
    }

    // Alert reaction countdown
    if (this.idleTime > 6) {
      this.idleTime -= 2;
      const dir = SpriteEngine.getDirection(dx, dy);
      this.lastDirection = dir.name;
      this.spriteEngine.setSprite('idle', this.lastDirection, 0);
      return;
    }

    this.idleTime = 0;
    this.frameCount += 1;

    // Move step
    const dirInfo = SpriteEngine.getDirection(dx, dy);
    this.lastDirection = dirInfo.name;

    const stepSpeed = Math.min(this.config.speed, distance);
    const moveX = (dx / distance) * stepSpeed;
    const moveY = (dy / distance) * stepSpeed;

    this.corgiX += moveX;
    this.corgiY += moveY;

    // Clamp
    const half = 18;
    this.corgiX = Math.min(Math.max(half, this.corgiX), window.innerWidth - half);
    this.corgiY = Math.min(Math.max(half, this.corgiY), window.innerHeight - half);

    this.spriteEngine.setSprite('running', this.lastDirection, this.frameCount);
    this.updatePosition();
  }

  public teleportTo(x: number, y: number): void {
    this.corgiX = Math.min(Math.max(20, x), window.innerWidth - 20);
    this.corgiY = Math.min(Math.max(20, y), window.innerHeight - 20);
    this.targetX = this.corgiX;
    this.targetY = this.corgiY;
    this.updatePosition();
  }
}
