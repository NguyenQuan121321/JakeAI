// TypeScript Definitions for JakeAI

export type DirectionName = 'S' | 'SE' | 'E' | 'NE' | 'N' | 'NW' | 'W' | 'SW';

export type SpriteState = 'idle' | 'running' | 'alert';

export type JakeTheme = 'light' | 'dark' | 'auto';

export type JakeSpawnPosition =
  | 'bottom-right'
  | 'bottom-left'
  | 'top-right'
  | 'top-left'
  | 'center'
  | string;

export interface DirectionInfo {
  row: number;
  name: DirectionName;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'ai' | 'system';
  text: string;
  timestamp: string;
}

export interface GoBackendChatRequest {
  message: string;
  sessionId: string;
}

export interface GoBackendChatResponse {
  response?: string;
  reply?: string;
  message?: string;
  toolCalls?: Array<{
    tool: string;
    params: Record<string, unknown>;
  }>;
}

export interface JakeProps {
  backendUrl?: string;
  greeting?: string;
  position?: JakeSpawnPosition;
  speed?: number;
  theme?: JakeTheme;
  name?: string;
  persistPosition?: boolean;
  quickChips?: string[];
  enableSound?: boolean;
  className?: string;
  style?: React.CSSProperties;
}

export interface JakeAIApi {
  openChat: (x?: number, y?: number) => void;
  closeChat: () => void;
  toggleChat: () => void;
  say: (text: string) => void;
  showHint: (text: string, durationMs?: number) => void;
  moveTo: (x: number, y: number) => void;
  setSpeed: (speed: number) => void;
  version: string;
}

declare global {
  interface Window {
    JakeAI?: JakeAIApi;
    __JAKE_AI_INITIALIZED__?: boolean;
    webkitAudioContext?: typeof AudioContext;
  }
}
