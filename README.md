# JakeAI — Portfolio Hub Agent

JakeAI is an interactive developer portfolio companion and AI assistant. It provides an 8-directional animated pet sprite with an integrated chat interface to guide visitors, explain architecture and features, and execute live API test calls against portfolio projects (FinnApiGo, VovinamApiNode).

The frontend is implemented in TypeScript with support for both direct React component usage (optimized for Next.js / React deployments on Vercel) and zero-dependency single-script embedding (`jake.min.js`). The backend is designed for Go (Golang) to ensure low latency and high concurrency when proxying AI completions and executing project endpoints.

---

## Architecture Overview

```
JakeAI/
├── frontend/                    # Frontend module (TypeScript & React)
│   ├── src/
│   │   ├── components/          # React components (JakeAI, ChatModal)
│   │   ├── engine/              # Sprite and physics movement engines
│   │   ├── services/            # Go backend API client and mock fallback
│   │   ├── styles/              # Injected CSS stylesheet
│   │   ├── types.ts             # TypeScript interfaces and contracts
│   │   ├── index.ts             # React library entry point
│   │   └── standalone.ts        # Single-script IIFE entry point
│   ├── assets/                  # Spritesheets (corgi_idle.png, corgi_run.png)
│   ├── dist/                    # Production bundles (ESM, types, jake.min.js)
│   ├── demo/                    # Local demo page
│   ├── package.json
│   ├── rollup.config.js
│   └── tsconfig.json
├── backend/                     # Go backend module (API Gateway & LLM proxy)
├── .gitignore
└── README.md
```

---

## Key Capabilities

1. **8-Direction Sprite Engine**:
   - Custom spritesheets for 8-direction running (37x37px per frame, 6 frames per direction) and idle states (32x32px per direction).
   - Angle resolver mapping delta coordinates to South, South-East, East, North-East, North, North-West, West, and South-West.

2. **Decoupled Movement Loop**:
   - Independent animation cycle using `requestAnimationFrame` and viewport boundary clamping.
   - Decoupled from React state reconciliation to prevent unnecessary Virtual DOM re-renders.
   - Configurable speed, stopping distance threshold, and position persistence via `localStorage`.

3. **Integrated Chat Hub**:
   - Draggable floating window with minimize, restore, and close controls.
   - Built-in lightweight Markdown renderer supporting code blocks, inline code, links, lists, and formatting.
   - Session management and intelligent local fallback when running offline or without an active backend.

4. **Dual Distribution**:
   - **React Component**: Importable `<JakeAI />` with full TypeScript type definitions.
   - **Standalone Script**: Self-contained `jake.min.js` (~89KB) with embedded base64 assets, requiring zero external stylesheets or image files.

---

## Integration Guide

### 1. React / Next.js (Vercel)

```tsx
import React from 'react';
import { JakeAI } from './frontend/src';

export default function PortfolioPage() {
  return (
    <main>
      <h1>Portfolio</h1>
      {/* Portfolio content */}

      <JakeAI
        backendUrl="https://jakeai-api.yourdomain.com"
        greeting="Hi! I am Jake, your portfolio guide. Ask me about FinnApiGo or VovinamApiNode."
        position="bottom-right"
        speed={10}
        theme="dark"
        enableSound={true}
      />
    </main>
  );
}
```

### 2. Standalone HTML Embedding

Add the script tag before the closing `</body>` tag:

```html
<script
  src="https://your-domain.com/jake.min.js"
  data-backend="https://jakeai-api.your-domain.com"
  data-greeting="Hi! I am Jake, your portfolio guide."
  data-position="bottom-right"
  data-speed="10"
  data-theme="dark"
></script>
```

---

## Configuration Reference

| Property / Attribute | Type | Default | Description |
|---|---|---|---|
| `backendUrl` / `data-backend` | `string` | `""` | Target Go backend URL (`POST /chat`) |
| `greeting` / `data-greeting` | `string` | `"Hi! I'm Jake..."` | Initial message displayed in the chat interface |
| `position` / `data-position` | `string` | `"bottom-right"` | Initial spawn position (`bottom-right`, `bottom-left`, `top-right`, `top-left`, `center`) |
| `speed` / `data-speed` | `number` | `10` | Movement speed (pixels per animation step) |
| `theme` / `data-theme` | `'light' \| 'dark' \| 'auto'` | `'auto'` | Color palette theme |
| `name` / `data-name` | `string` | `'Jake'` | Assistant display name |
| `enableSound` / `data-sound` | `boolean` | `true` | Web Audio API synthesized interaction feedback |
| `persistPosition` / `data-persist` | `boolean` | `true` | Persist coordinates across page navigations in `localStorage` |

---

## Go Backend Contract

The frontend communicates with the Go backend via standard JSON:

### Request (`POST /chat`)
```json
{
  "message": "Explain the architecture of FinnApiGo",
  "sessionId": "jake-session-1725260000"
}
```

### Response
```json
{
  "response": "FinnApiGo is a high-performance financial API built with Go...",
  "toolCalls": [
    {
      "tool": "test_finnapi",
      "params": {
        "endpoint": "/api/v1/quote",
        "symbol": "AAPL"
      }
    }
  ]
}
```

---

## License

MIT License. Copyright (c) Nguyen Quan.
