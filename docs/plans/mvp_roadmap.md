# PD3r MVP Roadmap: Technical Debt → Containerization → UX

**Date:** 2026-03-03
**Status:** Proposed
**Scope:** Full path from current state to deployed MVP with UX

---

## Current State Assessment

### What Works Well
- **859 tests passing**, graph builds cleanly, zero TODO/FIXME in codebase
- 6-phase workflow (init → interview → requirements → drafting → review → complete) is functional end-to-end
- RAG knowledge base is **populated and working** (12 PDFs ingested, ChromaDB vector store active)
- LLM-driven intent classification with structured Pydantic v2 outputs
- Comprehensive tracing infrastructure (JSONL + readable logs with token/cost tracking)
- Session persistence via LangGraph checkpointer (MemorySaver)
- Multi-field extraction per user message (user can answer multiple questions at once)
- FES factor evaluation and QA review with LLM-based semantic evaluation
- Word/Markdown export functional
- Supervisory conditional fields are defined in intake_fields.py

### What Needs Work

| Category | Issue | Severity | Phase |
|----------|-------|----------|-------|
| **Architecture** | Heuristic routing still active in routing.py (ADR-006 violation) | HIGH | 1 |
| **Architecture** | 5 deprecated functions in pd3r_agent.py awaiting removal | MEDIUM | 1 |
| **Architecture** | `_route_interview_phase()` deprecated but still called | HIGH | 1 |
| **Performance** | Intent classification is 73% of LLM cost ($0.015/run) — oversized prompt + gpt-4o | HIGH | 1 |
| **Performance** | Message history grows unbounded — later LLM calls progressively more expensive | HIGH | 1 |
| **Performance** | State compaction functions defined but never called in graph | MEDIUM | 1 |
| **Code Quality** | `sys.path.insert` hack in generate_element_node.py imports from docs/ | HIGH | 1 |
| **Code Quality** | Inconsistent async patterns across nodes (4 different approaches) | MEDIUM | 1 |
| **Code Quality** | Deprecated `asyncio.get_event_loop()` in finalize_node.py (breaks Python 3.12+) | MEDIUM | 1 |
| **Code Quality** | Hardcoded `gpt-4o` in qa_review_node.py instead of config | LOW | 1 |
| **Code Quality** | Global mutable semaphore in qa_review_node.py | LOW | 1 |
| **Code Quality** | Duplicate `is_exit_intent` property in intent.py | LOW | 1 |
| **Code Quality** | Legacy `organization` field alongside `organization_hierarchy` in interview.py | LOW | 1 |
| **Deployment** | Hardcoded paths: `output/.sessions`, pyproject.toml read at import time | HIGH | 2 |
| **Deployment** | No startup validation — missing API key crashes on first LLM call | HIGH | 2 |
| **Deployment** | CLI-only interface — `input()` calls, print statements for output | HIGH | 2 |
| **Deployment** | File system export assumes local write access | MEDIUM | 2 |
| **Reliability** | No hallucination guard on RAG/QA prompts ("only cite provided context") | MEDIUM | 1 |
| **Reliability** | No cost/token budget limits — runaway conversations can be expensive | MEDIUM | 2 |
| **Reliability** | No model fallback if gpt-4o unavailable | LOW | 2 |
| **Testing** | VCR cassettes referenced in docs but directory is empty | MEDIUM | 1 |
| **Docs** | AGENTS.MD testing focus section stale (still says "2026-01-16") | LOW | 1 |
| **Docs** | ADR-006 status still "Proposed" — should be "Active" or "In Progress" | LOW | 1 |
| **Docs** | No documentation for src/agents/ module | LOW | 1 |
| **Docs** | IDEA-.md is a single-line placeholder | LOW | 1 |

---

## Phase 1: Technical Debt Remediation (1-2 weeks)

### 1.1 Remove Deprecated Code — DONE
- Deleted 5 deprecated backward-compat functions from pd3r_agent.py
- Cleaned up `__init__.py` exports
- `_route_interview_phase()` remains (still called by main graph, removal requires interview_agent integration)
- All 859 tests pass

### 1.2 Fix Import Hack — DONE
- Created `src/config/drafting_sections.py` (clean copy from docs/business_rules/)
- Removed all `sys.path.insert` hacks from generate_element_node.py and drafting_tools.py
- Migrated all 7 `from docs.business_rules.*` imports to `from src.config.*` across src/ and tests/
- Zero `docs.business_rules` references remain in src/ or tests/

### 1.3 Standardize Async Patterns — DONE
- Created `src/utils/async_compat.py` with `run_async()` utility
- Replaced all 5 ad-hoc async wrappers (answer_question, intent_classification, generate_element, qa_review, finalize)
- Removed deprecated `asyncio.get_event_loop()` from finalize_node.py
- All nodes now use consistent pattern

### 1.4 Enable State Compaction — DONE
- Wired `compact_after_interview()` into evaluate_fes_factors_node (interview→requirements transition)
- Wired `compact_after_element_approved()` into handle_draft_response_node (element approval)
- Compaction clears transient fields and summarizes element draft history

### 1.5 Fix Minor Code Quality Issues — DONE
- qa_review_node.py: Replaced hardcoded `ChatOpenAI(model="gpt-4o")` with `get_chat_model()`
- intent.py: Removed duplicate `is_exit_intent` property
- Removed unused `ChatOpenAI` import from qa_review_node.py
- Removed unused `asyncio` import from finalize_node.py

### 1.6 Improve Prompt Reliability — DONE
- answer_question.jinja: Strengthened hallucination guard ("Only cite information from the context provided above")
- rag_answer.jinja: Added "Do not invent or assume federal regulations not present in the retrieved context"

### 1.7 Update Stale Documentation — DONE
- AGENTS.MD: Updated "Current Focus" to reflect tech debt → containerization → UX roadmap
- docs/decisions/INDEX.md: Updated ADR-006 to "Active", added ADR-007 and ADR-008
- Deleted empty docs/decisions/IDEA-.md placeholder

### 1.8 Remaining Phase 1 Items
- [ ] Record VCR cassettes for critical integration test paths
- [ ] Create `docs/modules/agents.md` documenting pd3r_agent.py architecture
- [ ] Update docs/INDEX.md to reference agents module

### Acceptance Criteria — Phase 1
- [x] All 859 tests pass
- [x] No `sys.path.insert` in source code
- [x] All async wrappers use consistent pattern (src/utils/async_compat.py)
- [x] State compaction active at phase boundaries
- [x] Hardcoded model references replaced with configurable get_chat_model()
- [x] Hallucination guards on RAG/QA prompts
- [x] Documentation current and accurate
- [ ] VCR cassettes recorded for offline CI testing

---

## Phase 2: API Layer & Containerization (1-2 weeks)

### 2.1 FastAPI Application — DONE
Created `src/api/` with all core files:

```
src/api/
├── __init__.py          # Exports app
├── app.py               # FastAPI app with REST endpoints + WebSocket
├── serve.py             # CLI entry point (poetry run pd3r-api)
├── models.py            # Request/Response Pydantic models
├── session_manager.py   # SessionManager wrapping LangGraph graph
└── websocket.py         # WebSocket handler for streaming chat
```

**Endpoints implemented:**
```
POST   /sessions                        → Create new PD session
GET    /sessions/{id}                   → Get session state
DELETE /sessions/{id}                   → Delete session
POST   /sessions/{id}/message           → Send message, get agent response
GET    /sessions/{id}/draft             → Get draft state with elements
GET    /sessions/{id}/export?format=md  → Export as markdown or word bytes
WS     /sessions/{id}/stream            → WebSocket streaming chat
GET    /health                          → Health check
```

### 2.2 Settings & Configuration — DONE
Created `src/config/settings.py` with pydantic-settings `BaseSettings`:
- Validates `OPENAI_API_KEY` at startup (fail fast)
- Supports both `OPENAI_API_KEY` and `PD3R_OPENAI_API_KEY` env vars
- Configurable CORS origins, API host/port, session limits, paths
- `.env` file support

### 2.3 Export-to-Bytes Support — DONE
Added `export_to_markdown_bytes()` and `export_to_word_bytes()` to `src/tools/export_tools.py`:
- Return bytes directly instead of writing to filesystem
- Used by SessionManager for API export endpoint
- 11 new API tests all pass

### 2.4 Containerization — DONE
- `Dockerfile`: Python 3.11-slim, Poetry install, uvicorn entrypoint
- `docker-compose.yml`: pd3r service with .env, volume mounts, PostgreSQL commented for opt-in
- `.dockerignore`: excludes __pycache__, .env, tests, .git

### 2.5 Remaining Phase 2 Items
- [ ] Wire PostgreSQL checkpointer for persistent sessions (currently MemorySaver)
- [ ] Token budget per session (tracking + cutoff)
- [ ] Rate limiting per session
- [ ] PATCH /sessions/{id}/draft/elements/{name} — lock/unlock element
- [ ] POST /sessions/{id}/draft/elements/{name}/regenerate — regenerate with feedback

### Acceptance Criteria — Phase 2
- [x] FastAPI server starts and serves all endpoints (12 routes)
- [x] WebSocket chat handler with interrupt/resume pattern
- [x] Export returns file bytes (markdown and word)
- [x] Docker container files created (Dockerfile, docker-compose.yml)
- [x] Startup validates config and fails fast on missing API key
- [x] 870 tests pass (859 existing + 11 new API tests)
- [ ] Sessions persist across server restarts (PostgreSQL checkpointer)
- [ ] Token budget enforced per session

---

## Phase 3: UX Implementation (2-3 weeks)

### 3.1 Architecture

```
┌──────────────────────────────────────────────────────┐
│                    Browser (React)                     │
│                                                        │
│  ┌─────────────────────┐  ┌────────────────────────┐  │
│  │    Chat Panel        │  │   Product Panel         │  │
│  │                      │  │                         │  │
│  │  [Agent messages]    │  │  ┌───────────────────┐  │  │
│  │  [User input]        │  │  │ Introduction  🔒  │  │  │
│  │  [Progress bar]      │  │  ├───────────────────┤  │  │
│  │  [Phase indicator]   │  │  │ Major Duties      │  │  │
│  │                      │  │  │ [editable area]   │  │  │
│  │                      │  │  ├───────────────────┤  │  │
│  │                      │  │  │ Factor 1     🔄   │  │  │
│  │                      │  │  │ [editable area]   │  │  │
│  │                      │  │  ├───────────────────┤  │  │
│  │                      │  │  │ ...more elements  │  │  │
│  │                      │  │  └───────────────────┘  │  │
│  │                      │  │                         │  │
│  │                      │  │  [Preview] [Export ▾]   │  │
│  └─────────────────────┘  └────────────────────────┘  │
└──────────────────────────────────────────────────────┘
         │                           │
         │  WebSocket (chat)         │  REST (draft ops)
         ▼                           ▼
┌──────────────────────────────────────────────────────┐
│                  FastAPI Backend                       │
│           (Phase 2 API layer)                         │
└──────────────────────────────────────────────────────┘
```

### 3.2 Tech Stack

- **Framework**: Next.js 14+ (App Router) or Vite + React — lean toward **Vite + React** for simplicity since this is a single-page app
- **State Management**: Zustand (lightweight, good for real-time state)
- **Styling**: Tailwind CSS + shadcn/ui components
- **Rich Text**: Tiptap editor (for editable draft sections)
- **WebSocket**: Native WebSocket API or socket.io-client
- **Export Preview**: react-pdf for in-browser preview
- **Markdown**: react-markdown for agent messages

### 3.3 Chat Panel Features

**Core:**
- Message stream (agent and user messages with timestamps)
- Text input with send button (Enter to send)
- Phase indicator pill (Interview → Requirements → Drafting → Review → Complete)
- Interview progress bar (X of Y fields collected)
- Typing indicator while agent is processing

**Enhanced:**
- Field extraction highlighting — when agent extracts fields, show them as chips in the message
- Question suggestions — based on current phase, show clickable suggested responses
- Message history with scroll-to-bottom

### 3.4 Product Panel Features

**Core:**
- Split into draft element sections (Introduction, Major Duties, Factor 1-9, Qualifications, etc.)
- Each section is a **bordered card** with:
  - Section title header
  - Editable content area (Tiptap rich text)
  - Status indicator: Empty | Draft | Approved | Locked
  - Lock toggle button (🔒 prevents regeneration)
  - Regenerate button (🔄 sends element back for regeneration with optional feedback)
- Sections appear as they are drafted (progressive reveal)
- Locked sections are read-only and visually distinct (subtle background color)

**Regeneration flow:**
1. User clicks 🔄 on a section
2. Optional: feedback modal appears ("What should change?")
3. API call: `POST /sessions/{id}/draft/elements/{name}/regenerate`
4. Section shows loading state
5. New content streams in via WebSocket
6. User can approve or regenerate again

**Preview & Export:**
- "Preview" button opens full-page formatted PD view (read-only, print-ready)
- "Export" dropdown: Download as .docx or .md
- "New PD" button: Starts fresh session (with confirmation dialog)

### 3.5 State Synchronization

The product panel must stay in sync with the backend draft state:

```
WebSocket events from backend:
  - phase_change: {phase: "drafting"}
  - element_started: {name: "introduction", index: 0}
  - element_content: {name: "introduction", content: "...", streaming: true}
  - element_complete: {name: "introduction", status: "draft"}
  - element_approved: {name: "introduction", status: "approved"}
  - qa_feedback: {name: "introduction", passed: false, feedback: "..."}

REST calls from frontend:
  - GET /draft/elements → initial state load
  - PATCH /draft/elements/{name} → lock/unlock, manual edit save
  - POST /draft/elements/{name}/regenerate → regenerate with feedback
```

### 3.6 Key UX Interactions

**Interview Phase:**
- Chat panel active, product panel shows skeleton/placeholder sections
- As user provides info, a sidebar or accordion could show "collected fields" summary
- Progress bar fills as fields are collected

**Drafting Phase:**
- Chat panel shows agent working messages ("I'm drafting the Introduction now...")
- Product panel sections fill in one by one with streaming content
- User can continue chatting while draft progresses (ask questions, provide feedback)

**Review Phase:**
- All sections visible in product panel
- User can click any section to provide feedback via chat or directly edit
- Lock sections they're satisfied with
- Regenerate individual sections with feedback

**Export:**
- Preview renders the complete PD with proper formatting
- Export downloads .docx with all approved content
- "Start New PD" resets both panels

### 3.7 Responsive Design

- Desktop: Side-by-side panels (chat left 40%, product right 60%)
- Tablet: Tabbed view (Chat | Product toggle)
- Mobile: Stacked with chat primary, product accessible via tab

### Acceptance Criteria — Phase 3
- [ ] Chat panel: send/receive messages via WebSocket, streaming responses
- [ ] Product panel: shows draft elements as they're generated
- [ ] Edit: inline editing of draft sections
- [ ] Lock/unlock: toggle per section, locked sections skip regeneration
- [ ] Regenerate: per-section regeneration with optional feedback
- [ ] Preview: full formatted PD view
- [ ] Export: download .docx and .md
- [ ] New PD: start fresh session
- [ ] Phase indicator and progress bar functional
- [ ] Works on desktop and tablet

---

## Phase 4: Polish & Production (1 week)

### 4.1 Reliability Testing
- End-to-end test: full interview → draft → review → export flow via API
- Load testing: 5 concurrent sessions
- Error recovery: kill backend mid-conversation, verify session resumes
- Edge cases: empty responses, very long messages, special characters

### 4.2 Observability
- Structured logging (JSON) to stdout for container log aggregation
- Health check endpoint: `GET /health` (DB connectivity, API key valid, vector store accessible)
- Session metrics: active sessions, avg tokens/session, avg duration

### 4.3 Security
- API key management (never expose OpenAI key to frontend)
- Input sanitization (prevent prompt injection via user messages)
- Session isolation (users can only access their own sessions)
- CORS configuration for production domain
- Rate limiting per IP/session

### 4.4 Documentation
- API documentation (auto-generated from FastAPI)
- UX component documentation
- Deployment guide (docker-compose for dev, Kubernetes manifests for prod)
- User guide for the PD writing interface

---

## Timeline Summary

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| **Phase 1**: Tech Debt | 1-2 weeks | Clean, performant, well-documented agent |
| **Phase 2**: API + Container | 1-2 weeks | Dockerized FastAPI backend with WebSocket |
| **Phase 3**: UX | 2-3 weeks | React app with chat + product panels |
| **Phase 4**: Polish | 1 week | Production-ready, tested, documented |
| **Total** | **5-8 weeks** to MVP |

---

## Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| LangGraph interrupt pattern doesn't map cleanly to WebSocket | HIGH | Prototype WS handler in Phase 2 before building full UX |
| Streaming token-by-token breaks structured output | MEDIUM | Use `astream_events` with event filtering; only stream chat messages, not structured outputs |
| Draft state sync between backend and frontend diverges | MEDIUM | Single source of truth in backend; frontend polls on reconnect |
| Cost overrun from long sessions | MEDIUM | Token budget per session with warning/cutoff |
| ChromaDB doesn't scale in container | LOW | ChromaDB is fine for single-instance; migrate to managed vector DB later if needed |
| Knowledge base PDFs not redistributable | LOW | Mount as volume; document PDF procurement in deployment guide |

---

## Architecture Decision: Why Not LangGraph Cloud?

LangGraph Cloud (LangGraph Platform) offers hosted graph execution with built-in:
- Persistent checkpointing
- Streaming API
- Session management
- Cron and background tasks

**We should evaluate this before building custom API layer.** If LangGraph Cloud meets our needs:
- Phase 2 becomes: "Deploy graph to LangGraph Cloud, build thin API proxy"
- Eliminates custom WebSocket handler, checkpointer setup, session management
- Trade-off: vendor lock-in, monthly cost, less control

**Recommendation:** Build Phase 2 with FastAPI but keep the graph portable. If LangGraph Cloud pricing is acceptable, migrate later.

---

## Open Questions for User

1. **Auth**: Does the UX need user authentication, or is it single-user demo?
2. **Persistence**: Should completed PDs be stored long-term, or is export-and-forget sufficient?
3. **Knowledge base**: Are the 12 PDFs currently ingested sufficient for MVP, or do more need to be added?
4. **Branding**: Any design requirements (colors, logo, agency branding)?
5. **Deployment target**: Local Docker, cloud VM, or managed platform (Vercel/Railway/Fly)?
