import React, { useState, useEffect, useRef, useCallback } from 'react';
import { ChatMessage, JakeProps } from '../types';
import { AIService } from '../services/aiService';

interface ChatModalProps extends JakeProps {
  isOpen: boolean;
  onClose: () => void;
  aiService: AIService;
  corgiPos?: { x: number; y: number };
}

export const ChatModal: React.FC<ChatModalProps> = ({
  isOpen,
  onClose,
  aiService,
  corgiPos,
  greeting = "Hi! I'm Jake, your portfolio guide 🐕\nAsk me about the projects or how I can help test APIs!",
  name = 'Jake',
  quickChips = [
    'Tell me about FinnApiGo 📈',
    'What is VovinamApiNode? 🥋',
    'How does JakeAI work? 🐕',
    'Test FinnApiGo stock endpoint'
  ],
  enableSound = true
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputVal, setInputVal] = useState<string>('');
  const [isMinimized, setIsMinimized] = useState<boolean>(false);
  const [isWaiting, setIsWaiting] = useState<boolean>(false);
  const [soundOn, setSoundOn] = useState<boolean>(enableSound);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Dragging state
  const dragRef = useRef<{ isDragging: boolean; startX: number; startY: number; posX: number; posY: number }>({
    isDragging: false,
    startX: 0,
    startY: 0,
    posX: 0,
    posY: 0
  });

  const getCurrentTime = (): string => {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const playAudio = useCallback((type: 'send' | 'receive' | 'open') => {
    if (!soundOn || typeof window === 'undefined') return;
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      const now = ctx.currentTime;

      if (type === 'send') {
        osc.frequency.setValueAtTime(440, now);
        osc.frequency.exponentialRampToValueAtTime(880, now + 0.08);
        gain.gain.setValueAtTime(0.08, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.08);
        osc.start(now);
        osc.stop(now + 0.08);
      } else {
        osc.frequency.setValueAtTime(600, now);
        osc.frequency.exponentialRampToValueAtTime(900, now + 0.12);
        gain.gain.setValueAtTime(0.1, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.12);
        osc.start(now);
        osc.stop(now + 0.12);
      }
    } catch {
      // AudioContext policy restrictions
    }
  }, [soundOn]);

  // Load chat history or initial greeting
  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      const saved = window.sessionStorage.getItem('jakeai_chat_history');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setMessages(parsed);
          return;
        }
      }
    } catch {}

    // Add initial greeting
    setMessages([
      {
        id: 'msg-init',
        sender: 'ai',
        text: greeting,
        timestamp: getCurrentTime()
      }
    ]);
  }, [greeting]);

  // Save history
  useEffect(() => {
    if (messages.length > 0 && typeof window !== 'undefined') {
      try {
        window.sessionStorage.setItem('jakeai_chat_history', JSON.stringify(messages));
      } catch {}
    }
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Handle open focus and initial positioning
  useEffect(() => {
    if (isOpen) {
      playAudio('open');
      setTimeout(() => inputRef.current?.focus(), 200);

      if (corgiPos && chatRef.current && !chatRef.current.style.left) {
        const chatWidth = 380;
        const chatHeight = 520;
        let left = corgiPos.x - chatWidth / 2;
        let top = corgiPos.y - chatHeight - 20;

        if (top < 20) top = corgiPos.y + 40;
        left = Math.max(16, Math.min(window.innerWidth - chatWidth - 16, left));
        top = Math.max(16, Math.min(window.innerHeight - chatHeight - 16, top));

        chatRef.current.style.left = `${left}px`;
        chatRef.current.style.top = `${top}px`;
        chatRef.current.style.right = 'auto';
        chatRef.current.style.bottom = 'auto';
      }
    }
  }, [isOpen, corgiPos, playAudio]);

  const handleSend = async (customText?: string) => {
    const text = (customText || inputVal).trim();
    if (!text || isWaiting) return;

    setInputVal('');
    const userMsg: ChatMessage = {
      id: 'msg-' + Date.now(),
      sender: 'user',
      text,
      timestamp: getCurrentTime()
    };

    setMessages((prev) => [...prev, userMsg]);
    playAudio('send');
    setIsWaiting(true);

    try {
      const responseText = await aiService.sendMessage(text);
      const aiMsg: ChatMessage = {
        id: 'msg-ai-' + Date.now(),
        sender: 'ai',
        text: responseText,
        timestamp: getCurrentTime()
      };
      setMessages((prev) => [...prev, aiMsg]);
      playAudio('receive');
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error';
      setMessages((prev) => [
        ...prev,
        {
          id: 'msg-err-' + Date.now(),
          sender: 'ai',
          text: `Woof! 🐾 Có trục trặc nhỏ: ${errorMsg}. Bạn có muốn hỏi về FinnApiGo hay VovinamApiNode không?`,
          timestamp: getCurrentTime()
        }
      ]);
    } finally {
      setIsWaiting(false);
    }
  };

  // Draggable logic
  const handleMouseDown = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('.jake-btn-icon')) return;
    if (!chatRef.current) return;

    const rect = chatRef.current.getBoundingClientRect();
    dragRef.current = {
      isDragging: true,
      startX: e.clientX,
      startY: e.clientY,
      posX: rect.left,
      posY: rect.top
    };

    const handleMouseMove = (moveEvent: MouseEvent) => {
      if (!dragRef.current.isDragging || !chatRef.current) return;
      const dx = moveEvent.clientX - dragRef.current.startX;
      const dy = moveEvent.clientY - dragRef.current.startY;

      let newX = dragRef.current.posX + dx;
      let newY = dragRef.current.posY + dy;

      const width = chatRef.current.offsetWidth;
      const height = chatRef.current.offsetHeight;
      newX = Math.max(10, Math.min(window.innerWidth - width - 10, newX));
      newY = Math.max(10, Math.min(window.innerHeight - height - 10, newY));

      chatRef.current.style.left = `${newX}px`;
      chatRef.current.style.top = `${newY}px`;
      chatRef.current.style.right = 'auto';
      chatRef.current.style.bottom = 'auto';
    };

    const handleMouseUp = () => {
      dragRef.current.isDragging = false;
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };

  const renderMarkdown = (rawText: string) => {
    let html = rawText
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    html = html.replace(/```([a-zA-Z0-9_]*)\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    html = html.replace(/(?:^|\n)[-*]\s+(.+)/g, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>');
    html = html.replace(/\n\n/g, '</p><p>');
    html = html.replace(/\n/g, '<br>');

    return { __html: `<p>${html}</p>` };
  };

  if (!isOpen) return null;

  return (
    <div
      ref={chatRef}
      id="jake-ai-chat"
      className={`jake-chat-window jake-chat-open ${isMinimized ? 'jake-chat-minimized' : ''}`}
      role="dialog"
      aria-label={`${name} Assistant`}
    >
      {/* Header */}
      <div id="jake-ai-header" className="jake-chat-header" onMouseDown={handleMouseDown}>
        <div className="jake-header-profile">
          <div className="jake-avatar-badge">
            🐕
            <span className="jake-status-dot" title="Online"></span>
          </div>
          <div className="jake-title-wrap">
            <span className="jake-title">{name}</span>
            <span className="jake-tagline">Go Backend & Portfolio Hub</span>
          </div>
        </div>

        <div className="jake-header-actions">
          <button
            type="button"
            className="jake-btn-icon"
            onClick={() => setSoundOn(!soundOn)}
            title={soundOn ? 'Mute' : 'Unmute'}
          >
            {soundOn ? '🔔' : '🔕'}
          </button>
          <button
            type="button"
            className="jake-btn-icon"
            onClick={() => setIsMinimized(!isMinimized)}
            title={isMinimized ? 'Restore' : 'Minimize'}
          >
            {isMinimized ? '□' : '─'}
          </button>
          <button
            type="button"
            className="jake-btn-icon"
            onClick={onClose}
            title="Close"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Messages */}
      {!isMinimized && (
        <>
          <div id="jake-ai-messages" className="jake-chat-messages">
            {messages.map((m) => (
              <div key={m.id} className={`jake-msg jake-msg-${m.sender}`}>
                <div
                  className="jake-msg-bubble"
                  dangerouslySetInnerHTML={m.sender === 'ai' ? renderMarkdown(m.text) : { __html: m.text }}
                />
                <div className="jake-msg-time">{m.timestamp}</div>
              </div>
            ))}

            {isWaiting && (
              <div className="jake-typing">
                <span className="jake-typing-dot"></span>
                <span className="jake-typing-dot"></span>
                <span className="jake-typing-dot"></span>
              </div>
            )}

            {/* Quick Chips if 1st message */}
            {messages.length === 1 && quickChips.length > 0 && (
              <div className="jake-quick-actions">
                {quickChips.map((chip, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className="jake-chip"
                    onClick={() => handleSend(chip)}
                  >
                    {chip}
                  </button>
                ))}
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Footer Form */}
          <form
            id="jake-ai-input-form"
            className="jake-chat-footer"
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
          >
            <input
              ref={inputRef}
              type="text"
              id="jake-ai-input"
              className="jake-chat-input"
              placeholder={`Ask ${name} about projects or test APIs...`}
              value={inputVal}
              onChange={(e) => setInputVal(e.target.value)}
              disabled={isWaiting}
            />
            <button
              type="submit"
              id="jake-ai-send"
              className="jake-chat-send"
              disabled={isWaiting || !inputVal.trim()}
              title="Send message"
            >
              <svg viewBox="0 0 24 24">
                <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
              </svg>
            </button>
          </form>
        </>
      )}
    </div>
  );
};
