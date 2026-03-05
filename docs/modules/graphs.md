# Graphs Reference

> **Last Updated**: 2026-01-15  
> **Module Path**: `src/graphs/`

---

## Overview

LangGraph workflow definitions live here. The main graph orchestrates a 6-phase conversational flow for PD generation. Drafting and QA now run in parallel across prerequisite-ready sections.

**Phases**: Init → Interview → Requirements → Drafting → Review → Complete

---

## Main Graph: `pd_graph`

The graph implements three phases:

```
Phase 1-2: Interview Collection
┌─────────────────────────────────────────────────────────────┐
│ START → init → user_input → classify_intent ─┬─> map_answers → prepare_next ─┐
│                      ↑                       │                               │
│                      └───────────────────────┴─> answer_question ───────────>│
│                      ↑                       │                               │
│                      └───────────────────────┴─> check_interview_complete ──>│
│                      │                                                       │
│                      └───────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────┘

Phase 3: Drafting (parallel-ready)
┌─────────────────────────────────────────────────────────────┐
│ evaluate_fes → gather_requirements → generate_element → qa_review (batch QA)
│      │                                ↑                  │
│      │                                └────────┬─────────┤
│      │                                         │         ↓
│      └─[prereq-ready set drafted in parallel]  │ handle_draft_response → advance_element → [next eligible or END]
└─────────────────────────────────────────────────────────────┘
```

---

## Nodes by Phase

### Phase 1: Init
| Node | Purpose |
|------|---------|
| `init` | Initialize conversation, greet user, detect resume/restart |

### Phase 2: Interview
| Node | Purpose |
|------|---------|
| `user_input` | Collect user input |
| `classify_intent` | Classify user intent via LLM |
| `map_answers` | Extract field values from user input |
| `prepare_next` | Determine next question to ask |
| `answer_question` | Answer user questions with RAG |
| `check_interview_complete` | Verify all required fields collected |

### Phase 3: Requirements
| Node | Purpose |
|------|---------|
| `evaluate_fes` | Evaluate FES factors for target grade |
| `gather_requirements` | Build requirements list for draft |

### Phase 4: Drafting
| Node | Purpose |
|------|---------|
| `generate_element` | Generate prerequisite-ready PD sections in parallel via LLM (with model escalation) |
| `qa_review` | Batch QA check against requirements for all ready sections |
| `handle_draft_response` | Process user approve/reject/revise, then jump to next ready section |
| `advance_element` | Move to next prerequisite-ready element or finalize |

### Phase 5: Review
| Node | Purpose |
|------|---------|
| `finalize` | Present complete document for final review |
| `handle_element_revision` | Process late revision requests |

### Phase 6: Complete
| Node | Purpose |
|------|---------|
| `end_conversation` | Clean conversation termination with write-another prompt |
| `handle_write_another` | Handle restart decision |
| `export_document` | Export to Markdown/Word |

---

## File Structure

| File | Purpose |
|------|---------|
| `__init__.py` | Exports `pd_graph`, `build_graph`, `compile_graph` |
| `main_graph.py` | Primary workflow definition with all nodes/edges |
| `export.py` | Mermaid syntax export with optional PNG generation |

---

## Building the Graph

```python
from src.graphs import pd_graph
from src.graphs.main_graph import build_graph, compile_graph

# Get the compiled default graph
app = pd_graph

# Or build with custom checkpointer
from langgraph.checkpoint.memory import MemorySaver
custom_graph = compile_graph(checkpointer=MemorySaver())
```

---

## Export Visualization

```python
from src.graphs.export import get_mermaid_syntax, export_graph_png
from src.graphs import pd_graph

# Get Mermaid syntax
mermaid = get_mermaid_syntax(pd_graph)
print(mermaid)

# Export to PNG (requires mermaid-cli)
export_graph_png(pd_graph, "output/graph.png")
```

Mermaid output is also written to `output/graphs/main_graph.mmd`.

---

## Routing Functions

Conditional edges use routing functions in `src/nodes/routing.py`:

| Function | Purpose |
|----------|---------|
| `route_after_init` | Route after initialization |
| `route_by_intent` | Main intent-based routing (phase-aware) |
| `route_should_end` | Check for conversation end |
| `route_after_qa` | Route based on QA pass/fail || `route_after_draft_response` | Route after user draft feedback |
| `route_after_advance_element` | Route to next element or finalize |
| `route_after_finalize` | Route after finalize (to user_input for response) |
| `route_after_element_revision` | Route after late revision |
| `route_after_export` | Route after export (write-another prompt) |
| `route_after_end_conversation` | Route to export or terminate |