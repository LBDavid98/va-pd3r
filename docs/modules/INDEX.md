# Module Reference Index

> **Last Updated**: 2026-03-05

---

## Core Modules

| Module | File | Description |
|--------|------|-------------|
| [models.md](models.md) | `src/models/` | 8 Pydantic v2 model files (source of truth) |
| [nodes.md](nodes.md) | `src/nodes/` | 18 node files, 17 exported node functions + 10 routing functions |
| [graphs.md](graphs.md) | `src/graphs/` | LangGraph 6-phase workflow |
| [prompts.md](prompts.md) | `src/prompts/` | Jinja2 prompt templates |
| [tools.md](tools.md) | `src/tools/` | Export, RAG, and knowledge base tools |
| [api.md](api.md) | `src/api/` | FastAPI REST + WebSocket API reference |
| [frontend.md](frontend.md) | `frontend/` | React SPA architecture, stores, WebSocket integration |

---

## Supporting Modules

| Module | File | Description |
|--------|------|-------------|
| Config | `src/config/` | Intake fields, FES factors, series templates |
| Constants | `src/constants.py` | Derived constants from config |
| Validation | `src/validation.py` | Input validation utilities |

---

## Business Rules (Data Files)

Located in `docs/business_rules/`:

| File | Purpose |
|------|---------|
| `fes_factor_levels.json` | FES factor level definitions and point values |
| `grade_cutoff_scores.json` | Grade determination score ranges |
| `gs2210_major_duties_templates.json` | IT Specialist duty templates |
| `other_significant_factors.json` | Additional evaluation factors |
| `intake_fields.py` | Python field definitions |
| `drafting_sections.py` | PD section configuration |

---

## Reading Order

1. **models.md** — Understand data contracts first (state, interview, intent, draft, FES)
2. **graphs.md** — See overall 6-phase workflow structure
3. **nodes.md** — Dive into node logic for each phase
4. **prompts.md** — Review prompt templates for LLM interactions
5. **tools.md** — Check export and RAG tool implementations
6. **api.md** — REST + WebSocket API reference
7. **frontend.md** — React component hierarchy, stores, WebSocket integration
