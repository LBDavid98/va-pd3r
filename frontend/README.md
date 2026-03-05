# PD3r Frontend

React + TypeScript SPA for the PD3r position description writing agent.

## Tech Stack

- **React 18** + TypeScript + Vite
- **Tailwind CSS v4** + shadcn/ui (radix-ui)
- **Zustand** for state management
- WebSocket (primary) + REST (fallback) communication

## Development

```bash
# Install dependencies
npm install

# Start dev server (port 5175, proxies /api to backend :8000)
npm run dev -- --port 5175

# Type check
npx tsc --noEmit

# Production build
npx vite build
```

The backend must be running on port 8000. Use `./scripts/dev.sh` from the project root to start both.

## Architecture

See [docs/modules/frontend.md](../docs/modules/frontend.md) for full architecture documentation including component hierarchy, store design, and WebSocket integration patterns.

## Key Directories

```
src/
├── api/          # REST client
├── components/   # React components (layout, chat, draft, ui)
├── hooks/        # useWebSocket, useAutoScroll
├── stores/       # Zustand stores (session, chat, draft, history)
├── types/        # TypeScript types mirroring backend models
├── lib/          # Constants, field metadata, utilities
└── utils/        # Auto-fill test scripts
```
