# PD3r Developer Handoff Checklist

> **Created**: 2026-03-11
> **Status**: In Progress
> **Purpose**: Ensure PD3r can be picked up and maintained by another developer

---

## Codebase Readiness

### Documentation
- [x] README.md with quick start, architecture overview
- [x] CLAUDE.md with AI agent policies and coding standards
- [x] docs/INDEX.md — documentation hub with navigation
- [x] 7 module reference docs (api, frontend, graphs, models, nodes, prompts, tools)
- [x] 10 Architecture Decision Records (ADRs 003-011)
- [x] Business case with ROI analysis
- [x] Procedure guides (testing, new-node, debugging, graph-export)
- [x] .env.example with all variables documented
- [ ] Cloud migration plan (see [cloud_migration_plan.md](cloud_migration_plan.md))
- [ ] Production runbook (create after cloud deployment)
- [ ] API reference (auto-generate from FastAPI OpenAPI schema)

### Code Quality
- [x] Python type annotations on all functions
- [x] Pydantic v2 models for all data structures
- [x] Async-first architecture (httpx, not requests)
- [x] Custom exception hierarchy in `src/exceptions.py`
- [x] Prompt templates separated from logic (Jinja2 in `src/prompts/`)
- [x] No mock LLM implementations (ADR-005)
- [x] No heuristic routing (ADR-006)
- [x] God methods decomposed (ADR-009)
- [x] Backend-authoritative status (ADR-010)
- [x] Structured agent visibility (ADR-011)

### Testing
- [x] 899+ tests passing (`poetry run pytest -q`)
- [x] Unit, integration, and end-to-end test coverage
- [x] Frontend type-checks clean (`npx tsc --noEmit`)
- [x] Frontend builds clean (`npx vite build`)
- [x] Testing phase controls documented (PD3R_STOP_AT, PD3R_SKIP_QA)
- [ ] CI pipeline running tests automatically (needs GitHub Actions)

### Infrastructure
- [x] Backend Dockerfile (Python 3.11-slim)
- [x] Frontend Dockerfile (Node 20 + nginx multi-stage)
- [x] docker-compose.yml (backend + frontend + optional Postgres)
- [x] Poetry lock file for reproducible Python builds
- [x] package-lock.json for reproducible frontend builds
- [ ] Kubernetes manifests
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] IaC templates (Terraform/CloudFormation)

---

## Knowledge Transfer

### Architecture Overview

```
pd3r/
├── src/                    # Python backend (18.8K LOC)
│   ├── api/                # FastAPI REST + WebSocket (app.py, websocket.py, session_manager.py)
│   ├── graphs/             # LangGraph workflow (main_graph.py — 19 nodes, 6 phases)
│   ├── nodes/              # Node implementations (23 files, one per node)
│   ├── models/             # Pydantic v2 state models (source of truth)
│   ├── prompts/templates/  # Jinja2 prompt templates (9 files)
│   ├── config/             # Settings, interview fields, FES factors, series templates
│   ├── tools/              # LLM tools, RAG, vector store, export
│   └── utils/              # LLM client, context builders, tracing
├── frontend/               # React 19 + Vite + Tailwind v4 + shadcn
│   ├── src/components/     # UI components (chat panel, draft panel, phase accordion)
│   ├── src/stores/         # Zustand state (session, chat, draft, history)
│   └── src/hooks/          # WebSocket, auto-scroll, export
├── tests/                  # 43 test files (12.7K LOC)
├── knowledge/              # RAG knowledge base (ChromaDB + source PDFs)
├── docs/                   # 36+ markdown docs
└── scripts/                # Dev, testing, and analysis scripts
```

### Key Concepts

1. **LangGraph Workflow**: The agent runs as a 6-phase state machine (init → interview → requirements → drafting → review → complete). Each phase has multiple nodes. The graph is defined in `src/graphs/main_graph.py`.

2. **Checkpointing**: Every node transition is checkpointed (SQLite or Postgres). Sessions survive server restarts. Resume is automatic via `Command(resume=...)`.

3. **WebSocket Streaming**: The primary chat interface uses WebSocket (`/sessions/{id}/stream`). Messages stream token-by-token. REST endpoints exist as fallback.

4. **Element Lifecycle**: Draft elements go through: generating → generated → qa_review → approved/needs_revision → (rewrite if needed). Status is always set by the backend (ADR-010).

5. **RAG Knowledge Base**: 12+ HR policy PDFs embedded in ChromaDB. Questions during interview are answered with document citations. Ingestion script: `scripts/ingest_knowledge.py`.

6. **Prompt Templates**: All LLM prompts are Jinja2 templates in `src/prompts/templates/`. Nodes import and render them — never define prompts inline.

### Critical Files (Start Here)

| File | Why |
|------|-----|
| `src/graphs/main_graph.py` | The entire workflow — nodes, edges, routing |
| `src/models/state.py` | AgentState — the source of truth for all state |
| `src/api/session_manager.py` | How sessions are created, resumed, and state is extracted |
| `src/api/websocket.py` | WebSocket protocol — message types, streaming |
| `src/config/settings.py` | All configuration with env var mapping |
| `src/config/intake_fields.py` | 30+ interview questions with conditional logic |
| `src/config/drafting_sections.py` | PD sections, word count targets, QA rules |

### Common Tasks

| Task | How |
|------|-----|
| Add an interview question | Edit `src/config/intake_fields.py`, add field definition |
| Add a new PD section | Edit `src/config/drafting_sections.py`, add section + QA criteria |
| Modify a prompt | Edit the Jinja2 template in `src/prompts/templates/` |
| Add a new node | Follow `docs/procedures/new-node.md` |
| Change LLM model | Set `OPENAI_DEFAULT_MODEL` env var |
| Add knowledge docs | Place PDF in `knowledge/unprocessed_pdfs/`, run `scripts/ingest_knowledge.py` |
| Debug a session | Enable `PD3R_TRACING=true`, run `scripts/analyze_trace.py` |

### Policies to Enforce

These are architectural invariants. Violating them will create regressions:

1. **No Mock LLM** — Every LLM call must be real. Tests use VCR cassettes or live calls.
2. **No Heuristic Routing** — Don't add if/else routing based on phase or intent. LLM decides via tool selection.
3. **No God Methods** — API handlers stay under 75 lines. Extract to helpers.
4. **Backend Authoritative** — Frontend never sets element status. Backend confirms via `element_update`.
5. **Structured Visibility** — Agent state communicated via `activity_update`, not suppressed chat messages.

---

## Environment Setup for New Developer

### Prerequisites
- Python 3.11+
- Node.js 20+
- Poetry (`pip install poetry`)
- OpenAI API key

### First Run
```bash
# Clone
git clone <repo-url> pd3r && cd pd3r

# Backend
poetry install
cp .env.example .env
# Edit .env — add OPENAI_API_KEY

# Frontend
cd frontend && npm install && cd ..

# Run both
./scripts/dev.sh
# Backend: http://localhost:8000
# Frontend: http://localhost:5175

# Run tests
poetry run pytest -q
cd frontend && npx tsc --noEmit
```

### Reading Order
1. This checklist (you're here)
2. `CLAUDE.md` — Policies and coding standards
3. `docs/INDEX.md` — Documentation navigation
4. `docs/modules/INDEX.md` — Module reference
5. `src/graphs/main_graph.py` — The workflow
6. `src/models/state.py` — The state model

---

## Open Items for New Developer

### Must Do (Before Production)
- [ ] **Enterprise ID / Multi-User Auth** (see cloud_migration_plan.md Phase 2)
  - [ ] User model + session ownership (user_id on sessions)
  - [ ] Auth middleware (header-based for SSOi, JWT for VA IAM)
  - [ ] WebSocket authentication
  - [ ] Audit trail (who/what/when)
- [ ] **Section 508 Compliance** (see cloud_migration_plan.md Phase 3)
  - [ ] aria-live regions for chat messages and status updates
  - [ ] aria-labels on all icon-only buttons
  - [ ] Keyboard accessibility (convert div/span onClick to buttons)
  - [ ] Semantic landmarks (main, aside labels, skip nav)
  - [ ] Color contrast verification
  - [ ] axe-core + VoiceOver testing
- [ ] Set up CI/CD pipeline (GitHub Actions — see cloud_migration_plan.md Phase 5)
- [ ] Migrate to PostgreSQL for cloud deployment
- [ ] Configure cloud secret management for API keys
- [ ] Set up monitoring and alerting
- [ ] Production CORS configuration
- [ ] ATO documentation and security review

### Should Do (Quality of Life)
- [ ] Auto-generate OpenAPI docs from FastAPI (`/docs` endpoint is already available in dev)
- [ ] Add `pre-commit` hooks (ruff lint + format)
- [ ] Add `eslint-plugin-jsx-a11y` for accessibility linting in frontend
- [ ] Set up branch protection rules on GitHub
- [ ] Add frontend test framework (Vitest recommended)
- [ ] Load testing with realistic concurrent users
- [ ] Per-user rate limiting and LLM cost budgets

### Nice to Have (Future Features)
- [ ] Approval workflows (multi-reviewer)
- [ ] Organization-specific PD templates
- [ ] Session sharing between users (multi-user editing)
- [ ] Model swapping (Anthropic Claude, Azure OpenAI)
- [ ] Fine-tuned model for FES evaluation
- [ ] Batch PD generation from spreadsheet input
- [ ] User roles (HR specialist, manager, admin)
