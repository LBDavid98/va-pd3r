# PD3r Documentation Index

> **Last Updated**: 2026-03-10
> **Nickname**: Pete  
> **Purpose**: Chat agent that writes federal position descriptions using LangGraph

---

## Quick Navigation

| Section | Description |
|---------|-------------|
| [modules/INDEX.md](modules/INDEX.md) | Module reference docs |
| [procedures/INDEX.md](procedures/INDEX.md) | How-to guides |
| [decisions/INDEX.md](decisions/INDEX.md) | Architecture Decision Records |
| [plans/](plans/) | Implementation plans |
| [business_rules/](business_rules/) | FES factors, grade cutoffs, duty templates |

---

## Module Overview

| Module | Purpose | Status |
|--------|---------|--------|
| `src/main.py` | Entry point, CLI | ✅ Active |
| `src/api/` | FastAPI REST + WebSocket API | ✅ Active |
| `src/graphs/` | LangGraph workflow (6-phase conversation) | ✅ Active |
| `src/nodes/` | 17 node implementations (18 files) | ✅ Active |
| `src/models/` | Pydantic v2 models (source of truth) | ✅ Active |
| `src/prompts/` | Jinja2 prompt templates | ✅ Active |
| `src/config/` | Intake fields, FES factors, series templates | ✅ Active |
| `src/tools/` | 19 LLM-driven tools (4 categories) | ✅ Active |
| `src/agents/` | Unified PD3r agent (pd3r_agent.py) | ✅ Active |
| `frontend/` | React + TypeScript SPA (Vite + Tailwind v4) | ✅ Active |

---

## MVP Roadmap Status

See [plans/mvp_roadmap.md](plans/mvp_roadmap.md) for current roadmap.

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1: Tech Debt | ✅ Complete | Deprecated code removed, async standardized |
| Phase 2: API Layer | ✅ Complete | FastAPI + WebSocket, Docker containerization |
| Phase 3: React UX | ✅ Complete | Two-panel chat + product layout |
| Phase 4: UX Polish | ✅ Complete | Drafting fixes, intent classification improvements |
| Phase 5: Handoff | 🔄 Current | Documentation, cleanup, deployment prep |
| **Arch Remediation** | ✅ Complete | [architectural_remediation.md](plans/architectural_remediation.md) — ADRs [009](decisions/009-send-message-decomposition.md), [010](decisions/010-backend-authoritative-status.md), [011](decisions/011-structured-agent-visibility.md) |

---

## Key Files

- [AGENTS.MD](../AGENTS.MD) — AI agent instructions (read first)
- [README.md](../README.md) — Project overview and quick start
- [pyproject.toml](../pyproject.toml) — Dependencies & CLI scripts
- `.env.example` — Environment variable template

---

## Workflow Phases

PD3r operates in six phases:

1. **Init** — Greet user, detect resume/restart scenarios
2. **Interview** — Collect position information via conversational interview
3. **Requirements** — Evaluate FES factors, gather draft requirements
4. **Drafting** — Generate and QA review PD sections with model escalation
5. **Review** — Present complete document for final approval
6. **Complete** — Export to Word/Markdown, offer to write another

---

## Graph Visualization

Mermaid diagram is auto-exported to `output/graphs/main_graph.mmd`.

PNG export available via `src/graphs/export.py` (requires mermaid-cli + Pillow).

---

## Quick Reference for AI Agents

### QA System Constants
```python
# src/nodes/qa_review_node.py
QA_PASS_THRESHOLD = 0.8      # ≥80% confidence to pass
QA_REWRITE_THRESHOLD = 0.5   # <50% triggers rewrite
QA_CONCURRENCY_LIMIT = 4     # Max parallel LLM calls
```

### Before Any Task
```
□ Read AGENTS.MD (mandatory)
□ Read this INDEX.md
□ Identify affected modules from modules/INDEX.md
□ Check tests/ for existing test patterns
```

### Common Commands
```bash
# Run all tests
poetry run pytest -q

# Run with tracing
PD3R_TRACING=true poetry run python -m src.main

# Analyze trace
poetry run python scripts/analyze_trace.py --trace output/logs/<trace>.jsonl
```

---

## Procedures

- [procedures/testing.md](procedures/testing.md) — Running tests
- [procedures/new-node.md](procedures/new-node.md) — Adding a new node
- [procedures/debugging.md](procedures/debugging.md) — Debugging with traces
- [procedures/graph-export.md](procedures/graph-export.md) — Exporting graph visualization

---

## Decisions

Architecture Decision Records live in `decisions/`. Start with [decisions/INDEX.md](decisions/INDEX.md).
