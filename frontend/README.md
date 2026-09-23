# JakeAI Companion Widget SDK (`@jakeai/widget`)

Enterprise-grade embedded AI companion widget built with vanilla TypeScript and Shadow DOM for zero CSS bleed into host web applications. Features animated Corgi mascot states, multi-model chat streaming (SSE), and enterprise BYOK API key registration.

---

## Prerequisites

- **Node.js**: `22.x` or `24.x` (Tested and certified on Node v24.20.0)
- **npm**: `10.x` or `11.x` (Tested on npm 11.19.0)

---

## Quick Start & Development

### 1. Install Dependencies
Always use `npm ci` to install dependencies matching the authoritative lockfile:
```bash
cd frontend
npm ci
```

### 2. Start Local Development Playground
Starts the Vite dev server and opens the local playground (`index.html`):
```bash
npm run dev
```
- Local URL: `http://localhost:5173/`
- Serves the host application simulation with live Corgi launcher and BYOK vault.
- Fully compatible with Windows drive-letter casing (`E:\` and `e:\`) and Linux environments.

---

## Available Scripts

| Command | Description |
| :--- | :--- |
| `npm run dev` | Starts the Vite development server for the widget sandbox. |
| `npm run build` | Compiles TypeScript declarations and builds production library bundles (`dist/jake-ai-widget.es.js` and `dist/jake-ai-widget.umd.js`). |
| `npm run typecheck` | Runs strict static type checking with TypeScript (`tsc --noEmit`). |
| `npm test` | Runs the Vitest unit test suite. |
| `npm run test:coverage` | Runs Vitest with v8 code coverage reporting. |

---

## Architecture & Cross-Platform Path Normalization

- **Entry Point**: The library bundle entry is `src/index.ts`.
- **Playground Entry**: The development sandbox uses `src/playground.ts` loaded via `<script type="module" src="./src/playground.ts"></script>`, avoiding fragile inline HTML proxy modules.
- **Root Resolution**: `vite.config.ts` computes a canonical root via `realpathSync.native()` and `normalizePath()`, ensuring consistent resolution across Windows drive-letter representations and POSIX operating systems.
