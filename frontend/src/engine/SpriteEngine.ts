// High-Performance 8-Direction Sprite Animation Engine (TypeScript)
import { SPRITE_IDLE_BASE64, SPRITE_RUN_BASE64 } from '../assets';
import { DirectionInfo, DirectionName, SpriteState } from '../types';

export const DIRECTIONS: Record<DirectionName, DirectionInfo> = {
  S:  { row: 0, name: 'S' },
  SE: { row: 1, name: 'SE' },
  E:  { row: 2, name: 'E' },
  NE: { row: 3, name: 'NE' },
  N:  { row: 4, name: 'N' },
  NW: { row: 5, name: 'NW' },
  W:  { row: 6, name: 'W' },
  SW: { row: 7, name: 'SW' },
};

const SECTOR_TO_DIR: DirectionName[] = ['E', 'SE', 'S', 'SW', 'W', 'NW', 'N', 'NE'];

export class SpriteEngine {
  public element: HTMLElement;
  public idleSrc: string;
  public runSrc: string;
  public currentState: SpriteState = 'idle';
  public currentDirection: DirectionName = 'S';
  public currentFrame: number = 0;
  private activeBgUrl: string = '';

  public readonly idleFrameSize: number = 32;
  public readonly runFrameSize: number = 37;
  public readonly runTotalFrames: number = 6;

  constructor(element: HTMLElement, customSprites: { idle?: string; run?: string } = {}) {
    this.element = element;
    this.idleSrc = customSprites.idle || SPRITE_IDLE_BASE64;
    this.runSrc = customSprites.run || SPRITE_RUN_BASE64;

    this.element.style.backgroundRepeat = 'no-repeat';
    this.element.style.imageRendering = 'pixelated';
    this.setSprite('idle', 'S', 0);
  }

  /**
   * Angle to 8-direction converter (0° East, 90° South, 180° West, 270° North)
   */
  public static getDirection(dx: number, dy: number): DirectionInfo {
    if (Math.abs(dx) < 0.001 && Math.abs(dy) < 0.001) {
      return DIRECTIONS.S;
    }

    const rad = Math.atan2(dy, dx);
    let deg = rad * (180 / Math.PI);
    if (deg < 0) deg += 360;

    const sector = Math.floor((deg + 22.5) / 45) % 8;
    const dirName = SECTOR_TO_DIR[sector] || 'S';
    return DIRECTIONS[dirName] || DIRECTIONS.S;
  }

  /**
   * Updates CSS sprite frame on the target HTMLElement
   */
  public setSprite(state: SpriteState, direction: DirectionName, frameIndex: number = 0): void {
    const dirInfo = DIRECTIONS[direction] || DIRECTIONS.S;
    const row = dirInfo.row;

    if (state === 'running') {
      const frame = frameIndex % this.runTotalFrames;
      const posX = -(frame * this.runFrameSize);
      const posY = -(row * this.runFrameSize);

      if (this.activeBgUrl !== this.runSrc) {
        this.element.style.backgroundImage = `url("${this.runSrc}")`;
        this.activeBgUrl = this.runSrc;
      }
      this.element.style.width = `${this.runFrameSize}px`;
      this.element.style.height = `${this.runFrameSize}px`;
      this.element.style.backgroundPosition = `${posX}px ${posY}px`;
    } else {
      // Idle state
      const posY = -(row * this.idleFrameSize);

      if (this.activeBgUrl !== this.idleSrc) {
        this.element.style.backgroundImage = `url("${this.idleSrc}")`;
        this.activeBgUrl = this.idleSrc;
      }
      this.element.style.width = `${this.idleFrameSize}px`;
      this.element.style.height = `${this.idleFrameSize}px`;
      this.element.style.backgroundPosition = `0px ${posY}px`;
    }

    this.currentState = state;
    this.currentDirection = direction;
    this.currentFrame = frameIndex;
  }
}
