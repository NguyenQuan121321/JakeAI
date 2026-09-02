# JakeAI 🐕 — Portfolio Hub Agent

JakeAI is an autonomous, GPU-accelerated Corgi pet companion and AI chat hub designed for developer portfolios.

Built with **TypeScript + React Component** for smooth integration on **Vercel**, with a **Go (Golang)** backend for high-performance AI proxying and live API testing (**FinnApiGo**, **VovinamApiNode**).

---

## 🏗️ Architecture

```
JakeAI/
├── frontend/                    # TypeScript + React Component & Standalone Bundle
│   ├── src/
│   │   ├── components/          # React Components (<JakeAI />, <ChatModal />)
│   │   ├── engine/              # Hardware-Accelerated 60-120 FPS Sprite & Physics
│   │   ├── services/            # Go Backend AI Client & Fallback Mock Engine
│   │   ├── styles/              # Scoped CSS with Dark/Light Themes
│   │   └── standalone.ts        # Single-file <script> entry (Zero dependencies)
│   ├── assets/                  # Corgi idle and running spritesheets
│   ├── dist/                    # Bundled React library (ESM) + jake.min.js
│   ├── demo/                    # Interactive portfolio demo playground
│   ├── package.json
│   ├── rollup.config.js
│   └── tsconfig.json
├── backend/                     # (Upcoming Go Backend: Gemini API + FinnApiGo/VovinamApiNode Proxy)
├── .gitignore
└── README.md
```

---

## 🚀 Quick Usage in React / Next.js (Vercel)

```tsx
import { JakeAI } from './frontend/src';

export default function App() {
  return (
    <div className="portfolio">
      <h1>Developer Portfolio</h1>

      {/* JakeAI Corgi Companion */}
      <JakeAI
        backendUrl="https://jakeai-api.yourdomain.com"
        greeting="Hi! I'm Jake, your portfolio guide 🐕"
        position="bottom-right"
        speed={10}
        theme="dark"
      />
    </div>
  );
}
```

Or embed directly into any HTML site with a single `<script>` tag:

```html
<script
  src="https://your-domain.com/jake.min.js"
  data-backend="https://jakeai-api.your-domain.com"
  data-greeting="Hi! I'm Jake, your portfolio guide 🐕"
  data-position="bottom-right"
></script>
```

---

## 📄 License

MIT License © Nguyen Quan
