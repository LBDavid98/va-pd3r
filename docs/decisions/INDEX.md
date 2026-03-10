# Architecture Decision Records Index

> **Last Updated**: 2026-03-10

---

## Active Decisions

| ADR | Title | Status |
|-----|-------|--------|
| [003](003-graph-export.md) | Auto-export graph PNG with timestamp | Accepted |
| [004](004-testing-phase-controls.md) | Testing Phase Controls (STOP_AT/SKIP_QA) | Accepted |
| [005](005-no-mock-llm.md) | No Mock LLM Implementations | Accepted |
| [006](006-llm-driven-routing.md) | LLM-Driven Routing (No Heuristics) | Active |
| [007](007-no-heuristic-decisions.md) | No Heuristic Decision Making | Accepted |
| [008](008-qa-content-caching.md) | QA Content Caching | Accepted |
| [009](009-send-message-decomposition.md) | send_message() Decomposition | Accepted |
| [010](010-backend-authoritative-status.md) | Backend-Authoritative Element Status | Accepted |
| [011](011-structured-agent-visibility.md) | Structured Agent Visibility | Accepted |

---

## Implicit Decisions (Reflected in Code)

The following decisions are implemented but not yet documented as ADRs:

| Decision | Implementation |
|----------|----------------|
| LangGraph Orchestration | 6-phase workflow in `src/graphs/main_graph.py` |
| Pydantic v2 Models | Source of truth in `src/models/` |
| Jinja2 Prompts | Templates in `src/prompts/templates/` |
| Config-Driven Fields | Definitions in `src/config/` |
| FES Factor Evaluation | 9-factor system in `src/config/fes_factors.py` |
| Interview-Based Collection | Field-by-field guided interview |
| Dual-Path Question Answering | RAG for HR questions, LLM for process questions |
| Draft Content in Approval Prompts | QA node shows full content before approval |

---

## ADR Template

```markdown
# ADR-XXX: Title

## Status
Proposed | Accepted | Deprecated | Superseded

## Context
What is the issue we're addressing?

## Decision
What did we decide to do?

## Consequences
What are the results of this decision?
```
