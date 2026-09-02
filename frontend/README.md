# JakeAI Frontend 🐕 (TypeScript & React)

An interactive, GPU-accelerated Corgi pet sprite with an integrated AI chat bubble designed for developer portfolios.

Supports **both native React / Next.js on Vercel** and **single-file `<script>` tag embedding** on any website.

---

## ✨ Features

- 🐾 **8-Directional Corgi Sprites**: Custom Corgi spritesheets for 8-direction running (37×37 frames) and idle animations (32×32 frames).
- ⚡ **Decoupled 60-120 FPS Physics Loop**: Hardware-accelerated GPU transforms (`translate3d`), running outside React re-render cycles for zero lag on portfolio pages.
- ⚛️ **Native React / Next.js Component**: First-class TypeScript component `<JakeAI />` ready to drop into your Vercel React portfolio.
- 📦 **Zero-Dependency Single Script Bundle**: Also compiles into `dist/jake.min.js` (~89KB minified with embedded base64 sprites).
- 💬 **AI Chat Bubble**: Draggable glassmorphic modal, Markdown code highlighter, typing indicator, sound synth (Web Audio API), and mobile collapse.
- 🐹 **Go Backend Ready**: Pre-configured for high-performance Golang backend endpoints (`POST /chat`), with built-in fallback mock testing.

---

## 🚀 Usage

### Option 1: In a React / Next.js Portfolio (Vercel)

```tsx
import React from 'react';
import { JakeAI } from 'jakeai';

export default function Portfolio() {
  return (
    <main>
      <h1>Nguyen Quan's Portfolio</h1>
      {/* Your portfolio sections (FinnApiGo, VovinamApiNode) */}

      {/* JakeAI Assistant */}
      <JakeAI
        backendUrl="https://jakeai-api.yourdomain.com"
        greeting="Hi! I'm Jake, your portfolio guide 🐕\nAsk me about FinnApiGo or VovinamApiNode!"
        position="bottom-right"
        speed={10}
        theme="dark"
        enableSound={true}
      />
    </main>
  );
}
```

### Option 2: Single `<script>` Tag Embedding

Add to any HTML page before `</body>`:

```html
<script
  src="https://your-domain.com/jake.min.js"
  data-backend="https://jakeai-api.your-domain.com"
  data-greeting="Hi! I'm Jake, your portfolio guide 🐕"
  data-position="bottom-right"
  data-speed="10"
  data-theme="dark"
></script>
```

---

## ⚙️ Props & Configuration

| Property / Attribute | Type | Default | Description |
|---|---|---|---|
| `backendUrl` / `data-backend` | `string` | `""` | Go Backend API endpoint (`POST /chat`) |
| `greeting` / `data-greeting` | `string` | `"Hi! I'm Jake..."` | Initial welcome message in chat |
| `position` / `data-position` | `string` | `"bottom-right"` | Spawn position (`bottom-right`, `bottom-left`, `top-right`, `top-left`, `center`) |
| `speed` / `data-speed` | `number` | `10` | Movement speed (pixels per step) |
| `theme` / `data-theme` | `'light' \| 'dark' \| 'auto'` | `'auto'` | Color theme |
| `name` / `data-name` | `string` | `'Jake'` | Assistant name |
| `enableSound` / `data-sound` | `boolean` | `true` | Synthesized audio chimes on message & click |
| `persistPosition` / `data-persist` | `boolean` | `true` | Save position in `localStorage` |

---

## 🐹 Go Backend API Contract

The frontend connects to the Go backend via standard JSON:

### Request (`POST /chat`):
```json
{
  "message": "Tell me about FinnApiGo stock endpoint",
  "sessionId": "jake-abc123-1725260000"
}
```

### Response:
```json
{
  "response": "📈 FinnApiGo offers real-time stock data...",
  "toolCalls": [
    {
      "tool": "test_finnapi",
      "params": { "endpoint": "/api/v1/quote", "symbol": "AAPL" }
    }
  ]
}
```

---

## 🛠️ Build & Development

```bash
# Install dependencies
npm install

# Build TypeScript types and bundles
npm run build

# Watch mode
npm run dev
```

---

## 📁 Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── JakeAI.tsx          # Main React Component
│   │   └── ChatModal.tsx       # Draggable Chat UI & Markdown renderer
│   ├── engine/
│   │   ├── SpriteEngine.ts     # 8-direction sprite animation engine
│   │   └── MovementEngine.ts   # 60-120 FPS GPU movement loop
│   ├── services/
│   │   └── aiService.ts        # Go backend connector & fallback mock
│   ├── styles/
│   │   └── styles.ts           # Injected CSS stylesheet
│   ├── assets.ts               # Embedded base64 sprites
│   ├── types.ts                # TypeScript type definitions
│   ├── index.ts                # React package export
│   └── standalone.ts           # Standalone IIFE bundle entry
├── assets/
│   ├── corgi_idle.png          # 8-direction idle spritesheet (32×256)
│   └── corgi_run.png           # 8-direction run spritesheet (222×296)
├── dist/
│   ├── index.js                # React ESM library
│   ├── index.d.ts              # TypeScript declarations
│   ├── jake.js                 # Standalone bundle
│   └── jake.min.js             # Minified standalone bundle (~89KB)
├── demo/
│   └── index.html              # Interactive demo page
├── package.json
├── rollup.config.js
└── tsconfig.json
```
