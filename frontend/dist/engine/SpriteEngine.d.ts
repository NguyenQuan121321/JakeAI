import { DirectionInfo, DirectionName, SpriteState } from '../types';
export declare const DIRECTIONS: Record<DirectionName, DirectionInfo>;
export declare class SpriteEngine {
    element: HTMLElement;
    idleSrc: string;
    runSrc: string;
    currentState: SpriteState;
    currentDirection: DirectionName;
    currentFrame: number;
    private activeBgUrl;
    readonly idleFrameSize: number;
    readonly runFrameSize: number;
    readonly runTotalFrames: number;
    constructor(element: HTMLElement, customSprites?: {
        idle?: string;
        run?: string;
    });
    /**
     * Angle to 8-direction converter (0° East, 90° South, 180° West, 270° North)
     */
    static getDirection(dx: number, dy: number): DirectionInfo;
    /**
     * Updates CSS sprite frame on the target HTMLElement
     */
    setSprite(state: SpriteState, direction: DirectionName, frameIndex?: number): void;
}
