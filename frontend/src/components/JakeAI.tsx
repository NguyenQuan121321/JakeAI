import React, { useEffect, useRef, useState, useMemo } from 'react';
import { JakeProps } from '../types';
import { injectStyles } from '../styles/styles';
import { MovementEngine } from '../engine/MovementEngine';
import { AIService } from '../services/aiService';
import { ChatModal } from './ChatModal';

export const JakeAI: React.FC<JakeProps> = (props) => {
  const {
    backendUrl = '',
    theme = 'auto',
    name = 'Jake',
    className = '',
    style = {}
  } = props;

  const corgiRef = useRef<HTMLDivElement>(null);
  const movementEngineRef = useRef<MovementEngine | null>(null);
  const [isChatOpen, setIsChatOpen] = useState<boolean>(false);
  const [badgeVisible, setBadgeVisible] = useState<boolean>(false);
  const [corgiCoord, setCorgiCoord] = useState<{ x: number; y: number }>({ x: 100, y: 100 });

  const aiService = useMemo(() => new AIService(backendUrl), [backendUrl]);

  useEffect(() => {
    aiService.setBackendUrl(backendUrl);
  }, [backendUrl, aiService]);

  useEffect(() => {
    // 1. Inject Styles
    injectStyles(theme);

    // 2. Initialize Movement Engine
    if (corgiRef.current) {
      const engine = new MovementEngine(corgiRef.current, props, (x, y) => {
        setCorgiCoord({ x, y });
        setIsChatOpen((prev) => {
          const next = !prev;
          if (next) setBadgeVisible(false);
          return next;
        });
      });
      movementEngineRef.current = engine;

      // 3. Animation Loop (60-120 FPS decoupled GPU loop)
      let animId: number;
      const onFrame = (time: number) => {
        engine.step(time);
        animId = requestAnimationFrame(onFrame);
      };
      animId = requestAnimationFrame(onFrame);

      // 4. Global window.JakeAI API
      if (typeof window !== 'undefined') {
        window.JakeAI = {
          openChat: (x, y) => {
            if (x && y) engine.teleportTo(x, y);
            setCorgiCoord({ x: engine.corgiX, y: engine.corgiY });
            setIsChatOpen(true);
            setBadgeVisible(false);
          },
          closeChat: () => {
            setIsChatOpen(false);
            setBadgeVisible(true);
          },
          toggleChat: () => {
            setCorgiCoord({ x: engine.corgiX, y: engine.corgiY });
            setIsChatOpen((prev) => !prev);
          },
          say: (text: string) => {
            // Can be extended to add directly to state
            console.log(`[JakeAI] say: ${text}`);
          },
          showHint: (text: string, duration?: number) => {
            engine.showHint(text, duration);
          },
          moveTo: (x: number, y: number) => {
            engine.teleportTo(x, y);
          },
          setSpeed: (speed: number) => {
            engine.config.speed = speed;
          },
          version: '1.0.0'
        };
      }

      return () => {
        cancelAnimationFrame(animId);
      };
    }
  }, [theme]);

  const handleCloseChat = () => {
    setIsChatOpen(false);
    setBadgeVisible(true);
  };

  const handleOpenFromBadge = () => {
    if (movementEngineRef.current) {
      setCorgiCoord({
        x: movementEngineRef.current.corgiX,
        y: movementEngineRef.current.corgiY
      });
    }
    setIsChatOpen(true);
    setBadgeVisible(false);
  };

  return (
    <div
      id="jake-ai-container"
      className={`jake-ai-root jake-theme-${theme} ${className}`}
      style={style}
    >
      {/* Corgi Pet Element */}
      <div
        ref={corgiRef}
        id="jake-ai-corgi"
        className="jake-corgi-sprite"
        role="button"
        tabIndex={0}
        aria-label={`${name} the Corgi companion`}
      />

      {/* Floating Reopen Badge */}
      <button
        type="button"
        id="jake-ai-badge"
        className={`jake-reopen-badge ${badgeVisible && !isChatOpen ? 'jake-badge-visible' : ''}`}
        onClick={handleOpenFromBadge}
      >
        <span>🐕 Chat with {name}</span>
      </button>

      {/* Interactive Chat Window */}
      <ChatModal
        {...props}
        isOpen={isChatOpen}
        onClose={handleCloseChat}
        aiService={aiService}
        corgiPos={corgiCoord}
      />
    </div>
  );
};
