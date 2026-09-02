import { SpriteEngine } from './SpriteEngine';
import { DirectionName, JakeProps } from '../types';
export declare class MovementEngine {
    element: HTMLElement;
    spriteEngine: SpriteEngine;
    config: Required<JakeProps>;
    corgiX: number;
    corgiY: number;
    targetX: number;
    targetY: number;
    lastDirection: DirectionName;
    frameCount: number;
    idleTime: number;
    lastTimestamp: number;
    isChatOpen: boolean;
    isPaused: boolean;
    private onCorgiClick?;
    private tooltipEl?;
    private hintTimer?;
    constructor(element: HTMLElement, props?: JakeProps, onCorgiClick?: (x: number, y: number) => void);
    private initPosition;
    private setupListeners;
    private createTooltip;
    showHint(text?: string, durationMs?: number): void;
    updatePosition(): void;
    step(timestamp: number): void;
    tick(): void;
    teleportTo(x: number, y: number): void;
}
