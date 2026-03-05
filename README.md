# PD3r (Pete)

> **AI-powered position description writer for the federal government**
>
> VHA Digital Health Office

Pete is a conversational AI agent that helps HR specialists and hiring managers create complete, OPM-compliant position descriptions through a guided interview. It collects position details, evaluates FES factors, drafts all PD elements, runs automated quality checks, and exports formatted documents — reducing a multi-day process to under an hour.

---

## Capabilities

| Capability | Description |
|-----------|-------------|
| **Conversational Interview** | Guided collection of 30+ position fields through natural language chat |
| **FES Factor Evaluation** | Automatic evaluation of all 9 FES factors with grade recommendation |
| **OPM-Compliant Drafting** | Generates 8 PD elements using series-specific templates for 100+ GS series |
| **Automated QA** | Every draft element validated against requirements; auto-rewrites on failure |
| **Real-Time Streaming** | WebSocket-based chat with live response streaming |
| **Session Persistence** | Resume interrupted sessions or write additional PDs without restarting |
| **Field Overrides** | Inline editing of any collected data point |
| **RAG Knowledge Base** | Answers HR policy and process questions during the interview |
| **Export** | Production-ready Word (.docx) and Markdown (.md) output |

---

## Workflow

```
┌─────────┐    ┌───────────┐    ┌──────────────┐    ┌──────────┐    ┌────────┐    ┌──────────┐
│  Init    │───▶│ Interview │───▶│ Requirements │───▶│ Drafting │───▶│ Review │───▶│ Complete │
│          │    │           │    │              │    │          │    │        │    │          │
│ Greeting │    │ 30+ fields│    │ FES eval     │    │ 8 elems  │    │ Final  │    │ Export   │
│ Resume?  │    │ Q&A       │    │ Grade calc   │    │ QA check │    │ Revise │    │ Another? │
└─────────┘    └───────────┘    └──────────────┘    └──────────┘    └────────┘    └──────────┘
```

### Interview Phase
- Collects position title, series, grade, organization, duties, scope, supervision level, and 20+ additional fields
- Supports mid-interview questions ("What's an FES factor?") and answer corrections
- Conditional fields — supervisory questions only appear when relevant

### Requirements & FES
- Evaluates 9 FES factors (Knowledge, Supervision Received, Responsibility, Complexity, Scope & Effect, plus 4 Other Significant Factors)
- Each factor assessed across 3–6 defined levels with point values
- Grade recommendation calculated from total points

### Drafting & QA
- Generates Introduction, Major Duties, Supervisory Responsibilities, Qualifications, Physical Demands, Other Significant Factors, Position Relationships, and Performance Standards
- Each element validated against requirements with severity-rated checks (critical / warning / info)
- Automatic rewrite on critical QA failure

### Export
- Word (.docx) with professional formatting, headers, and structure
- Markdown (.md) for portability and version control

---

## Tech Stack

### Architecture

```
┌─────────────────────────────────────────────────┐
│                   Frontend                       │
│  React 18 · TypeScript · Tailwind v4 · shadcn   │
│  Zustand state · WebSocket streaming             │
├─────────────────────────────────────────────────┤
│               FastAPI Backend                    │
│  15 REST endpoints · WebSocket · Session mgmt    │
│  Docker · Nginx · PostgreSQL (optional)          │
├─────────────────────────────────────────────────┤
│             LangGraph AI Pipeline                │
│  19 nodes · 10 prompt templates · RAG pipeline   │
│  OpenAI LLM · ChromaDB vectors · Checkpointing  │
├─────────────────────────────────────────────────┤
│              Domain Knowledge                    │
│  30+ intake fields · 9 FES factors (350+ levels) │
│  100+ GS series templates · OPM business rules   │
└─────────────────────────────────────────────────┘
```

### Frontend
| Technology | Purpose |
|-----------|---------|
| React 18 + TypeScript | Component-based UI |
| Vite | Development server and production builds |
| Tailwind CSS v4 | Utility-first styling, VA branding |
| shadcn/ui (Radix) | Accessible component library |
| Zustand | Lightweight state management (4 stores) |
| WebSocket API | Real-time bidirectional streaming |

### Backend
| Technology | Purpose |
|-----------|---------|
| Python 3.11+ | Async-first, type-annotated |
| FastAPI | REST API + WebSocket endpoints |
| LangGraph | Agent orchestration (19-node state graph) |
| Pydantic v2 | Data validation, API schemas, LLM structured output |
| Jinja2 | Prompt templating (10 templates) |
| ChromaDB | Vector store for RAG knowledge base |
| python-docx | Word document generation |

### Infrastructure
| Technology | Purpose |
|-----------|---------|
| Docker Compose | Container orchestration (backend + frontend + optional DB) |
| Nginx | Frontend static serving and SPA routing |
| PostgreSQL | Production checkpointing (SQLite for development) |
| OpenAI API | LLM provider (architecture supports model swapping) |

---

## Application Metrics

| Metric | Value |
|--------|-------|
| Automated tests | 866+ |
| Test code | 12,500+ lines |
| Backend modules | 74 |
| Frontend components | 32 |
| API endpoints | 15 REST + WebSocket |
| LangGraph nodes | 19 |
| Interview fields | 30+ (with conditional logic) |
| GS series supported | 100+ |
| FES factor levels | 350+ |
| Architecture Decision Records | 10+ |

---

## UI Overview

The application uses a three-panel layout:

- **Left sidebar** — Phase accordion showing workflow progress, collected fields, and FES evaluation status
- **Center panel** — Chat interface for conversational interaction with Pete
- **Right panel** — Draft product view showing generated PD elements with status indicators, QA results, and export controls

VA-branded with official VA blue (#003F72), VA logo, and Section 508-aware component library.

---

## Running the Application

### Prerequisites
- Python 3.11+, Node.js 20+, Poetry
- OpenAI API key in `.env`

### Quick Start

```bash
# Install backend dependencies
poetry install

# Install frontend dependencies
cd frontend && npm install && cd ..

# Configure environment
cp .env.example .env
# Add OPENAI_API_KEY to .env

# Start both servers
./scripts/dev.sh
# Backend: http://localhost:8000
# Frontend: http://localhost:5175
```

### Docker

```bash
docker compose up --build
# Frontend: http://localhost:80
# Backend: http://localhost:8000
```

### Tests

```bash
# Run all tests
poetry run pytest -q

# Frontend type check
cd frontend && npx tsc --noEmit
```

---

## Project Structure

```
pd3r/
├── frontend/                  # React/TypeScript UI
│   ├── src/
│   │   ├── components/        # 32 components (layout, chat, draft, ui)
│   │   ├── stores/            # Zustand stores (session, chat, draft, history)
│   │   ├── hooks/             # WebSocket, auto-scroll, export
│   │   └── types/             # TypeScript API types
│   └── public/                # VA logo assets
├── src/                       # Python backend
│   ├── api/                   # FastAPI app, session manager, WebSocket
│   ├── graphs/                # LangGraph workflow (main_graph.py)
│   ├── nodes/                 # 19 node implementations + routing
│   ├── models/                # 8 Pydantic model files (~65 models)
│   ├── prompts/templates/     # 10 Jinja2 prompt templates
│   ├── config/                # FES factors, intake fields, series templates
│   ├── tools/                 # Export (Word/MD), RAG, embeddings
│   └── utils/                 # LLM client, state compaction, async compat
├── tests/                     # 866+ pytest tests
├── docs/                      # Documentation, ADRs, business rules
│   ├── business_case.md       # Cost analysis and internal capability argument
│   └── INDEX.md               # Documentation navigation
├── docker-compose.yml         # Container orchestration
└── pyproject.toml             # Dependencies and CLI configuration
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [Business Case](docs/business_case.md) | Cost analysis, ROI, and build-vs-buy argument |
| [Documentation Index](docs/INDEX.md) | Full documentation navigation |
| [Architecture Decisions](docs/) | ADRs for key technical choices |

---

## Contact

**VHA Digital Health Office**
Built by David Hook (David.Hook2@va.gov)
