# JakeAI Frontend

Frontend module for JakeAI — an embeddable Corgi pet companion with an integrated AI chat interface designed for developer portfolios.

The module provides both a native React component for React and Next.js applications and a bundled standalone script (`dist/jake.min.js`) for embedding into any HTML page via a single `<script>` tag.

---

## Technical Specifications

- **Language**: TypeScript (strict type checking, full interface definitions).
- **Rendering**: Hardware-accelerated DOM CSS (`position: fixed`, direct coordinate mapping, pixelated image rendering).
- **Performance**: Decoupled animation loop running via `requestAnimationFrame` outside React reconciliation cycles to prevent unnecessary Virtual DOM re-renders.
- **Assets**: Spritesheets embedded as Base64 strings directly in the bundled output for zero external network requests.
- **Bundle Size**: ~89KB minified (including full 8-direction sprite data).
- **Backend Compatibility**: Designed for Go (Golang) REST endpoints with fallback mock engine.

---

## Spritesheet Layout

The sprite engine handles two separate spritesheets:

1. **Idle Spritesheet (`assets/corgi_idle.png`)**:
   - Total Dimensions: 32 x 256 px.
   - Frame Dimensions: 32 x 32 px per direction.
   - Directions (8 vertical rows): S (0), SE (1), E (2), NE (3), N (4), NW (5), W (6), SW (7).

2. **Running Spritesheet (`assets/corgi_run.png`)**:
   - Total Dimensions: 222 x 296 px.
   - Frame Dimensions: 37 x 37 px per frame.
   - 6 horizontal animation frames per direction row across 8 vertical rows.

---

## Installation & Usage

### 1. React / Next.js Component

```tsx
import React from 'react';
import { JakeAI } from 'jakeai';

export default function App() {
  return (
    <div className="portfolio-container">
      {/* Portfolio views */}
      <JakeAI
        backendUrl="https://api.yourdomain.com"
        greeting="Hi! I am Jake, your portfolio guide."
        position="bottom-right"
        speed={10}
        theme="dark"
        enableSound={true}
      />
    </div>
  );
}
```

### 2. Standalone Script Embedding

```html
<script
  src="https://yourdomain.com/jake.min.js"
  data-backend="https://api.yourdomain.com"
  data-greeting="Hi! I am Jake, your portfolio guide."
  data-position="bottom-right"
  data-speed="10"
  data-theme="dark"
></script>
```

---

## Configuration Properties

| Property | Data Attribute | Type | Default | Description |
|---|---|---|---|---|
| `backendUrl` | `data-backend` | `string` | `""` | Target backend URL (`POST /chat`) |
| `greeting` | `data-greeting` | `string` | `"Hi! I am Jake..."` | Initial message shown upon opening chat |
| `position` | `data-position` | `string` | `"bottom-right"` | Initial spawn position (`bottom-right`, `bottom-left`, `top-right`, `top-left`, `center`) |
| `speed` | `data-speed` | `number` | `10` | Movement speed in pixels per frame |
| `theme` | `data-theme` | `'light' \| 'dark' \| 'auto'` | `'auto'` | UI theme palette |
| `name` | `data-name` | `string` | `'Jake'` | Display name of the assistant |
| `enableSound` | `data-sound` | `boolean` | `true` | Synthesized audio feedback via Web Audio API |
| `persistPosition` | `data-persist` | `boolean` | `true` | Save and restore position from `localStorage` |

---

## Global JavaScript API

When loaded via the standalone script, `window.JakeAI` is exposed for programmatic control:

```typescript
// Open or close chat interface
window.JakeAI.openChat(x?: number, y?: number);
window.JakeAI.closeChat();
window.JakeAI.toggleChat();

// Send an assistant message
window.JakeAI.say("Here is an update.");

// Show a temporary speech bubble above the sprite
window.JakeAI.showHint("Exploring the codebase...", 3000);

// Teleport sprite to target coordinates
window.JakeAI.moveTo(500, 300);

// Update movement speed dynamically
window.JakeAI.setSpeed(12);
```

---

## Development & Build Commands

```bash
# Install development dependencies
npm install

# Build asset constants, React library, and standalone bundles
npm run build

# Type check TypeScript codebase
npm run typecheck

# Watch mode for active development
npm run dev
```

---

## File Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── JakeAI.tsx          # Main React component
│   │   └── ChatModal.tsx       # Draggable chat interface and Markdown parser
│   ├── engine/
│   │   ├── SpriteEngine.ts     # 8-direction sprite animation manager
│   │   └── MovementEngine.ts   # Mouse tracking and boundary clamping logic
│   ├── services/
│   │   └── aiService.ts        # Backend API connector and mock handler
│   ├── styles/
│   │   └── styles.ts           # Injected CSS stylesheet
│   ├── assets.ts               # Embedded Base64 spritesheet constants
│   ├── types.ts                # TypeScript interface declarations
│   ├── index.ts                # React ESM library export
│   └── standalone.ts           # IIFE standalone bundle entry
├── assets/
│   ├── corgi_idle.png          # Idle spritesheet
│   └── corgi_run.png           # Run spritesheet
├── dist/
│   ├── index.js                # ESM component bundle
│   ├── index.d.ts              # TypeScript type definitions
│   ├── jake.js                 # Unminified bundle
│   └── jake.min.js             # Minified production bundle
├── demo/
│   └── index.html              # Local testing environment
├── package.json
├── rollup.config.js
└── tsconfig.json
```

---

## License

MIT License. Copyright (c) Nguyen Quan.
