// Standalone Single-Script Bundle for JakeAI (TypeScript)
// For embedding into any website via <script src="jake.min.js"></script>
import { injectStyles } from './styles/styles';
import { MovementEngine } from './engine/MovementEngine';
import { AIService } from './services/aiService';
import { JakeProps, JakeTheme } from './types';

(function bootstrapJakeStandalone() {
  if (typeof window === 'undefined') return;
  if (window.__JAKE_AI_INITIALIZED__) return;
  window.__JAKE_AI_INITIALIZED__ = true;

  function parseConfig(): JakeProps {
    let script = document.currentScript as HTMLScriptElement | null;
    if (!script) {
      const scripts = document.querySelectorAll('script[src*="jake"]');
      if (scripts.length > 0) script = scripts[scripts.length - 1] as HTMLScriptElement;
    }

    const ds = (script && script.dataset) ? script.dataset : {};

    return {
      backendUrl: ds.backend || '',
      greeting: ds.greeting || "Hi! I'm Jake, your portfolio guide 🐕\nAsk me about the projects or how I can help test APIs!",
      position: ds.position || 'bottom-right',
      speed: ds.speed ? parseFloat(ds.speed) : 10,
      theme: (ds.theme as JakeTheme) || 'auto',
      name: ds.name || 'Jake',
      persistPosition: ds.persist !== 'false',
      enableSound: ds.sound !== 'false'
    };
  }

  const config = parseConfig();

  function mount() {
    injectStyles(config.theme);

    const root = document.createElement('div');
    root.id = 'jake-ai-container';
    root.className = `jake-ai-root jake-theme-${config.theme}`;
    document.body.appendChild(root);

    // Corgi Element
    const corgiEl = document.createElement('div');
    corgiEl.id = 'jake-ai-corgi';
    corgiEl.className = 'jake-corgi-sprite';
    corgiEl.setAttribute('role', 'button');
    corgiEl.setAttribute('tabindex', '0');
    root.appendChild(corgiEl);

    // AI Service
    const aiService = new AIService(config.backendUrl);

    // Chat Window HTML
    const chatEl = document.createElement('div');
    chatEl.id = 'jake-ai-chat';
    chatEl.className = 'jake-chat-window';
    chatEl.innerHTML = `
      <div id="jake-ai-header" class="jake-chat-header">
        <div class="jake-header-profile">
          <div class="jake-avatar-badge">🐕<span class="jake-status-dot" title="Online"></span></div>
          <div class="jake-title-wrap">
            <span class="jake-title">${config.name}</span>
            <span class="jake-tagline">Go Backend & Portfolio Hub</span>
          </div>
        </div>
        <div class="jake-header-actions">
          <button type="button" class="jake-btn-icon" id="jake-btn-sound" title="Sound">🔔</button>
          <button type="button" class="jake-btn-icon" id="jake-btn-min" title="Minimize">─</button>
          <button type="button" class="jake-btn-icon" id="jake-btn-close" title="Close">✕</button>
        </div>
      </div>
      <div id="jake-ai-messages" class="jake-chat-messages"></div>
      <form id="jake-ai-input-form" class="jake-chat-footer">
        <input type="text" id="jake-ai-input" class="jake-chat-input" placeholder="Ask ${config.name} about projects..." autocomplete="off" />
        <button type="submit" id="jake-ai-send" class="jake-chat-send" title="Send">
          <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
        </button>
      </form>
    `;

    // Badge
    const badgeEl = document.createElement('button');
    badgeEl.id = 'jake-ai-badge';
    badgeEl.className = 'jake-reopen-badge';
    badgeEl.innerHTML = `<span>🐕 Chat with ${config.name}</span>`;

    root.appendChild(chatEl);
    root.appendChild(badgeEl);

    const messagesEl = chatEl.querySelector('#jake-ai-messages') as HTMLElement;
    const inputEl = chatEl.querySelector('#jake-ai-input') as HTMLInputElement;
    const sendBtn = chatEl.querySelector('#jake-ai-send') as HTMLButtonElement;
    const soundBtn = chatEl.querySelector('#jake-btn-sound') as HTMLButtonElement;
    const minBtn = chatEl.querySelector('#jake-btn-min') as HTMLButtonElement;
    const closeBtn = chatEl.querySelector('#jake-btn-close') as HTMLButtonElement;

    let soundOn = config.enableSound !== false;
    let isChatOpen = false;
    let isMin = false;
    let isWaiting = false;

    function playAudio(type: string) {
      if (!soundOn) return;
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
      } catch {}
    }

    function renderMarkdown(text: string): string {
      let html = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      html = html.replace(/```([a-zA-Z0-9_]*)\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>');
      html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
      html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
      html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
      html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
      html = html.replace(/(?:^|\n)[-*]\s+(.+)/g, '<li>$1</li>');
      html = html.replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>');
      html = html.replace(/\n\n/g, '</p><p>');
      html = html.replace(/\n/g, '<br>');
      return `<p>${html}</p>`;
    }

    function appendMessage(sender: 'user' | 'ai', text: string) {
      const msg = document.createElement('div');
      msg.className = `jake-msg jake-msg-${sender}`;
      const bubble = document.createElement('div');
      bubble.className = 'jake-msg-bubble';
      bubble.innerHTML = sender === 'ai' ? renderMarkdown(text) : text;
      const time = document.createElement('div');
      time.className = 'jake-msg-time';
      time.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

      msg.appendChild(bubble);
      msg.appendChild(time);
      messagesEl.appendChild(msg);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function showTyping() {
      const t = document.createElement('div');
      t.className = 'jake-typing';
      t.id = 'jake-typing-indicator';
      t.innerHTML = '<span class="jake-typing-dot"></span><span class="jake-typing-dot"></span><span class="jake-typing-dot"></span>';
      messagesEl.appendChild(t);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function hideTyping() {
      const t = document.getElementById('jake-typing-indicator');
      if (t) t.remove();
    }

    function openChat(x?: number, y?: number) {
      isChatOpen = true;
      isMin = false;
      chatEl.classList.remove('jake-chat-minimized');
      chatEl.classList.add('jake-chat-open');
      badgeEl.classList.remove('jake-badge-visible');

      if (x && y && !chatEl.style.left) {
        let l = x - 190;
        let t = y - 540;
        if (t < 20) t = y + 40;
        chatEl.style.left = `${Math.max(16, Math.min(window.innerWidth - 396, l))}px`;
        chatEl.style.top = `${Math.max(16, Math.min(window.innerHeight - 536, t))}px`;
      }

      playAudio('open');
      setTimeout(() => inputEl.focus(), 200);
    }

    function closeChat() {
      isChatOpen = false;
      chatEl.classList.remove('jake-chat-open');
      badgeEl.classList.add('jake-badge-visible');
    }

    // Initial greeting
    appendMessage('ai', config.greeting || "Hi! I'm Jake 🐕");

    // Quick chips
    const chipsWrap = document.createElement('div');
    chipsWrap.className = 'jake-quick-actions';
    ['Tell me about FinnApiGo 📈', 'What is VovinamApiNode? 🥋', 'Test FinnApiGo stock endpoint'].forEach((chip) => {
      const c = document.createElement('button');
      c.type = 'button';
      c.className = 'jake-chip';
      c.textContent = chip;
      c.onclick = () => {
        inputEl.value = chip;
        sendBtn.click();
      };
      chipsWrap.appendChild(c);
    });
    messagesEl.appendChild(chipsWrap);

    // Form submit
    chatEl.querySelector('#jake-ai-input-form')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const val = inputEl.value.trim();
      if (!val || isWaiting) return;

      inputEl.value = '';
      appendMessage('user', val);
      playAudio('send');

      isWaiting = true;
      sendBtn.disabled = true;
      showTyping();

      try {
        const reply = await aiService.sendMessage(val);
        hideTyping();
        appendMessage('ai', reply);
        playAudio('receive');
      } catch (err: unknown) {
        hideTyping();
        appendMessage('ai', `Woof! 🐾 Error: ${err instanceof Error ? err.message : String(err)}`);
      } finally {
        isWaiting = false;
        sendBtn.disabled = false;
        inputEl.focus();
      }
    });

    closeBtn.onclick = closeChat;
    badgeEl.onclick = () => openChat(engine.corgiX, engine.corgiY);
    minBtn.onclick = () => {
      isMin = !isMin;
      if (isMin) {
        chatEl.classList.add('jake-chat-minimized');
        minBtn.textContent = '□';
      } else {
        chatEl.classList.remove('jake-chat-minimized');
        minBtn.textContent = '─';
        inputEl.focus();
      }
    };
    soundBtn.onclick = () => {
      soundOn = !soundOn;
      soundBtn.textContent = soundOn ? '🔔' : '🔕';
    };

    // Movement engine
    const engine = new MovementEngine(corgiEl, config, (x, y) => {
      if (isChatOpen) closeChat();
      else openChat(x, y);
    });

    let animId: number = 0;
    function onFrame(t: number) {
      if (!corgiEl.isConnected) {
        cancelAnimationFrame(animId);
        return;
      }
      engine.step(t);
      animId = requestAnimationFrame(onFrame);
    }
    animId = requestAnimationFrame(onFrame);

    window.JakeAI = {
      openChat: (x, y) => openChat(x || engine.corgiX, y || engine.corgiY),
      closeChat,
      toggleChat: () => isChatOpen ? closeChat() : openChat(engine.corgiX, engine.corgiY),
      say: (text: string) => appendMessage('ai', text),
      showHint: (text: string, d?: number) => engine.showHint(text, d),
      moveTo: (x: number, y: number) => engine.teleportTo(x, y),
      setSpeed: (s: number) => { engine.config.speed = s; },
      version: '1.0.0'
    };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
  } else {
    mount();
  }
})();
