import React, { useEffect, useRef, useState, useMemo } from 'react';
import { JakeProps } from '../types';
import { injectStyles } from '../styles/styles';
import { MovementEngine } from '../engine/MovementEngine';
import { AIService } from '../services/aiService';
import { ChatModal } from './ChatModal';

export const DogHouseIcon: React.FC<{ className?: string }> = ({ className }) => (
  <svg viewBox="0 0 48 48" className={className} fill="none" xmlns="http://www.w3.org/2000/svg">
    {/* Base Grass */}
    <rect x="4" y="42" width="40" height="4" rx="2" fill="#2ed573" />
    {/* Wood Planks House */}
    <rect x="8" y="18" width="32" height="24" rx="2" fill="#d35400" />
    <rect x="10" y="20" width="28" height="22" fill="#e67e22" />
    <line x1="10" y1="27" x2="38" y2="27" stroke="#d35400" strokeWidth="1.5" />
    <line x1="10" y1="34" x2="38" y2="34" stroke="#d35400" strokeWidth="1.5" />
    {/* Red Roof */}
    <polygon points="24,2 2,19 7,20 24,6 41,20 46,19" fill="#c0392b" />
    <polygon points="24,5 5,20 9,20 24,8 39,20 43,20" fill="#e74c3c" />
    {/* Door Entrance */}
    <path d="M18 42 V28 A6 6 0 0 1 30 28 V42 Z" fill="#2c3e50" />
    <path d="M19 42 V29 A5 5 0 0 1 29 29 V42 Z" fill="#1a252f" />
    {/* Bone Plaque */}
    <rect x="20" y="22" width="8" height="3" rx="1.5" fill="#f5f6fa" />
    <circle cx="20" cy="23.5" r="1.5" fill="#f5f6fa" />
    <circle cx="28" cy="23.5" r="1.5" fill="#f5f6fa" />
  </svg>
);

export const JakeAI: React.FC<JakeProps> = (props) => {
  const {
    backendUrl = '',
    theme = 'auto',
    name = 'Jake',
    dogHouseImage,
    showDogHouse = true,
    className = '',
    style = {}
  } = props;

  const corgiRef = useRef<HTMLDivElement>(null);
  const movementEngineRef = useRef<MovementEngine | null>(null);
  const [isChatOpen, setIsChatOpen] = useState<boolean>(false);
  const [corgiCoord, setCorgiCoord] = useState<{ x: number; y: number }>({ x: 100, y: 100 });

  const aiService = useMemo(() => new AIService(backendUrl), [backendUrl]);

  useEffect(() => {
    aiService.setBackendUrl(backendUrl);
  }, [backendUrl, aiService]);

  useEffect(() => {
    injectStyles(theme);

    if (corgiRef.current) {
      const engine = new MovementEngine(corgiRef.current, props, (x, y) => {
        setCorgiCoord({ x, y });
        setIsChatOpen((prev) => !prev);
      });
      movementEngineRef.current = engine;

      let animId: number;
      const onFrame = (time: number) => {
        engine.step(time);
        animId = requestAnimationFrame(onFrame);
      };
      animId = requestAnimationFrame(onFrame);

      if (typeof window !== 'undefined') {
        window.JakeAI = {
          openChat: (x, y) => {
            if (x && y) engine.teleportTo(x, y);
            setCorgiCoord({ x: engine.corgiX, y: engine.corgiY });
            setIsChatOpen(true);
          },
          closeChat: () => {
            setIsChatOpen(false);
          },
          toggleChat: () => {
            setCorgiCoord({ x: engine.corgiX, y: engine.corgiY });
            setIsChatOpen((prev) => !prev);
          },
          say: (text: string) => {
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
  };

  const handleDogHouseClick = () => {
    if (movementEngineRef.current) {
      // Call Jake back to the dog house
      movementEngineRef.current.teleportTo(
        window.innerWidth - 85,
        window.innerHeight - 50
      );
      setCorgiCoord({
        x: window.innerWidth - 85,
        y: window.innerHeight - 50
      });
      movementEngineRef.current.showHint(`Woof! Welcome to ${name}'s house 🐾`, 3000);
    }
    setIsChatOpen((prev) => !prev);
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

      {/* Doghouse (Jake's Home) */}
      {showDogHouse && (
        <button
          type="button"
          id="jake-ai-doghouse"
          className="jake-doghouse"
          onClick={handleDogHouseClick}
          aria-label={`${name}'s Doghouse`}
        >
          {dogHouseImage ? (
            <img src={dogHouseImage} alt={`${name}'s Doghouse`} className="jake-doghouse-img" />
          ) : (
            <DogHouseIcon className="jake-doghouse-svg" />
          )}
          <span className="jake-doghouse-tooltip">{name}'s Home 🐾</span>
        </button>
      )}

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
