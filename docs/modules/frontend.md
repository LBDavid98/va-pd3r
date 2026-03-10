# Frontend Architecture

> Last Updated: 2026-03-10

React + TypeScript SPA in `frontend/`. Communicates with the backend via WebSocket (primary) and REST (fallback).

## Tech Stack

- **React 18** + **TypeScript** + **Vite**
- **Tailwind CSS v4** for styling
- **shadcn/ui** (via `radix-ui` monorepo) for components
- **Zustand** for state management
- **sonner** for toast notifications

## Component Hierarchy

```
App.tsx
├── AppShell (ResizablePanelGroup: left 35% / right 65%)
│   ├── Left Panel
│   │   ├── Header (VA logo, title, settings gear, history button)
│   │   ├── PhaseAccordion (workflow stepper sidebar)
│   │   ├── ChatPanel (message list + input)
│   │   │   ├── MessageList → MessageBubble
│   │   │   ├── TypingIndicator
│   │   │   └── ChatInput (with auto-fill: Option+Enter)
│   │   └── HistoryPanel (slide-over, right-anchored)
│   └── Right Panel
│       └── ProductPanel (OF-8 document view)
│           ├── DocumentHeader (coversheet grid)
│           ├── DraftSection × N (collapsible: QA + feedback + edit)
│           └── ExportBar (accept all + download)
├── SettingsDialog (3 tabs: LLM, Organization, Testing)
└── ui/ (13 shadcn components)
```

## State Management (Zustand)

### sessionStore (primary)
- Session lifecycle: `createSession()`, `resumeSession()`, `restartSession()`, `reset()`
- Phase tracking: `phase`, `state` (full `SessionState`)
- Field overrides: `setFieldOverride()` → PATCH backend + local optimistic update
- WebSocket: `wsSend` callback registered by ChatPanel, `wsRef` for structured sends
- Agent activity: `agentActivity` tracks current agent operation (cleared on `done`)
- Chat title: auto-generated from position metadata

### chatStore
- Message list with deduplication
- Typing indicator + 60s hung detection
- Methods: `addMessage()`, `setTyping()`, `checkHung()`, `clear()`

### draftStore
- Draft elements with intelligent merge on fetch:
  - Server content/status always wins
  - Local fields preserved: `locked`, `notes`, `edited`
  - Hand-edited content preserved (won't be overwritten by server)
  - QA review: prefers fresh server data, falls back to local
- Methods: `fetchDraft()`, `updateElement()`, `setElements()`, `clear()`

### historyStore (localStorage-persisted)
- Max 20 sessions, 200 messages each
- Supports resume (reloads messages + state) and download (with markdown fallback)

## WebSocket Integration

`useWebSocket.ts` manages the connection lifecycle:

1. **Connect** on session creation → auto-reconnect with exponential backoff (1s → 16s max)
2. **Ping/pong** every 30s to keep connection alive
3. **Message classification** (`classifyAgentMessage()`, ~28 lines) — minimal filter for content already shown elsewhere:
   - Suppresses draft content leaked into chat (shown in ProductPanel)
   - Suppresses FES evaluation detail, pipeline filler, interrupt prompts
   - All other messages shown as normal chat bubbles
   - See [ADR-011](../decisions/011-structured-agent-visibility.md) for rationale
4. **Activity tracking** — `activity_update` messages set `agentActivity` on sessionStore; cleared on `done`/`stopped`
5. **Element updates** — `element_update` messages update draft store (backend authoritative, see [ADR-010](../decisions/010-backend-authoritative-status.md))
6. **Structured actions** — `element_action` messages sent via raw `wsRef` for approve/reject/regenerate (bypasses LLM classification)
7. **Draft fetch** triggered on `agent_message` or `state_update` during drafting/review phases
8. **Stale session guard** — messages from previous sessions are ignored

## Key Patterns

### Field Override Flow
1. User edits field in InterviewFieldList or InitPhaseContent
2. `sessionStore.setFieldOverride()` stores locally + PATCHes backend
3. Pending overrides merged into `interview_data_values` for immediate display
4. `consumeFieldOverrides()` returns them for inclusion in next WS message
5. `updateState()` clears overrides once backend confirms values

### Draft Status Lifecycle
```
pending → drafted → qa_passed → approved
                  → needs_revision → (auto-rewrite) → drafted → ...
```
Status is always set by the backend via `element_update` messages. The frontend renders spinners when `agentActivity.element` matches the section name, replacing the old heuristic-based `isAgentProcessing` check.

### Export Fallback
When downloading from history and the server session has expired, the frontend builds a markdown file from locally-stored draft elements.

## File Map

| Path | Purpose |
|------|---------|
| `src/App.tsx` | Root: session init, WebSocket setup |
| `src/api/client.ts` | REST API client (fetch-based) |
| `src/hooks/useWebSocket.ts` | WebSocket connection + message handling |
| `src/hooks/useAutoScroll.ts` | Auto-scroll chat to bottom |
| `src/stores/*.ts` | Zustand stores (session, chat, draft, history) |
| `src/types/api.ts` | TypeScript types mirroring backend Pydantic models |
| `src/lib/constants.ts` | Phase order, labels, status colors |
| `src/lib/fieldMeta.ts` | Interview field metadata (labels, types) |
| `src/utils/autoFillScript.ts` | Test auto-fill data (3 scenarios) |
| `src/components/ui/` | shadcn/radix UI primitives |
