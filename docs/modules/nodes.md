# Nodes Reference

> **Last Updated**: 2026-01-25  
> **Module Path**: `src/nodes/`

---

## 🚀 LLM-Driven Routing Migration (In Progress)

**Phase 1 Complete**: The interview phase now has an LLM-driven agent in `src/agents/interview_agent.py` that uses tool selection instead of heuristic routing.

**New Pattern** (preferred):
```python
from src.agents.interview_agent import create_interview_agent

# LLM decides which tool to call based on state-aware prompts
agent = create_interview_agent()
result = await agent.invoke({"messages": [...]}, config)
```

**Deprecated Pattern** (being replaced):
```python
# ⚠️ DEPRECATED: Heuristic routing in routing.py
def _route_interview_phase(intent, state):  # Don't add new logic here
    if intent == "provide_information":
        return "map_answers"
    # ...
```

See: [ADR-006: LLM-Driven Routing](../decisions/006-llm-driven-routing.md), [Migration Plan](../plans/langgraph_migration_plan.md)

---

## ⛔ NO MOCK LLM POLICY ⛔

**All nodes that require LLM MUST call the real LLM. No exceptions.**

This is an architectural decision to ensure:
- Test behavior matches production behavior
- Prompt bugs are caught immediately
- No dual code paths that diverge over time

**Forbidden patterns:**
- `classify_intent_basic()` or similar pattern-matching fallbacks
- `try: llm_call() except: basic_fallback()`
- `if USE_LLM: llm() else: mock()`

**Required patterns:**
- Validate API key at node entry → `ConfigurationError` if missing
- All tests use VCR cassettes of real LLM responses
- No `except Exception: pass` that silently degrades

See: [ADR-005: No Mock LLM](../decisions/005-no-mock-llm.md)

---

## Overview

Nodes are the building blocks of the PD3r graph. Each node:
- Receives `AgentState` as input
- Returns state updates (dict) or uses `Command` for explicit routing
- Follows single-responsibility principle

---

## Node Files

| File | Node(s) | Purpose |
|------|---------|---------|
| `init_node.py` | `init_node` | Initialize conversation and greet user |
| `user_input_node.py` | `user_input_node` | Collect and validate user input |
| `intent_classification_node.py` | `intent_classification_node` | LLM-based intent classification |
| `map_answers_node.py` | `map_answers_node` | Extract field values from user input |
| `prepare_next_node.py` | `prepare_next_node` | Determine next question to ask |
| `answer_question_node.py` | `answer_question_node`, `answer_question_node_async` | Answer user questions |
| `check_interview_complete_node.py` | `check_interview_complete_node` | Verify all fields collected |
| `evaluate_fes_factors_node.py` | `evaluate_fes_factors_node` | Evaluate FES factors for grade |
| `gather_draft_requirements_node.py` | `gather_draft_requirements_node` | Build requirements list |
| `generate_element_node.py` | `generate_element_node` | Generate prerequisite-ready PD sections in parallel via LLM |
| `qa_review_node.py` | `qa_review_node`, `route_after_qa` | Parallel QA check for all ready sections |
| `handle_revision_node.py` | `handle_draft_response_node`, `advance_to_next_element_node` | Process user feedback and jump to next ready section |
| `finalize_node.py` | `finalize_node`, `handle_element_revision_request` | Final review and export prompt |
| `export_node.py` | `export_document_node` | Export to Markdown/Word |
| `handle_write_another_node.py` | `handle_write_another_node` | Handle "write another PD?" flow |
| `end_conversation_node.py` | `end_conversation_node` | Clean conversation termination |
| `routing.py` | `route_after_init`, `route_by_intent`, `route_should_end`, etc. | Routing logic |

---

## Nodes by Phase

### Phase 1: Init

#### `init_node`
Initializes conversation state, greets user, detects resume/restart scenarios.

```python
def init_node(state: AgentState) -> dict:
    # Returns: phase, interview_data, missing_fields, greeting message
```

### Phase 2: Interview

#### `user_input_node`
Collects user input from messages via LangGraph interrupt.

#### `intent_classification_node`
Uses LLM to classify user intent with **structured output** (`IntentClassification` Pydantic model).

Stores full classification in state:
- `last_intent`: Primary intent string for routing
- `intent_classification`: Full `IntentClassification` object for downstream nodes
- `_export_request`: Serialized export request (when intent is `request_export`)

**Intents**: `provide_information`, `ask_question`, `confirm`, `reject`, `modify_answer`, `request_restart`, `quit`, `request_export`, `unrecognized`

**Intent Clarifications (complete phase)**:
- `reject` = user declining ("no", "done", "no thanks", "I'm finished")
- `request_export` = explicit format requests only ("word", "markdown")

#### `map_answers_node`
Extracts field values from classified intent and updates interview data.

#### `prepare_next_node`
Determines next field to ask about based on missing/unconfirmed fields.

#### `answer_question_node`
Answers user questions using two paths:
- **RAG path** (`is_hr_specific: true`) - Queries OPM knowledge base for HR/classification questions
- **Non-RAG path** (`is_hr_specific: false`) - Uses detailed prompt for process questions

Reads intent from `state["intent_classification"]` to determine routing.

#### `check_interview_complete_node`
Verifies all required fields collected, transitions to requirements phase.

### Phase 3: Requirements

#### `evaluate_fes_factors_node`
Evaluates position against FES factors to determine appropriate levels.

#### `gather_draft_requirements_node`
Builds requirements list from FES evaluation and series templates with preamble context.

### Phase 4: Drafting

#### `generate_element_node`
Generates all prerequisite-ready sections in parallel (LLM calls batched). Uses prerequisites to pick the current element and keeps others in `drafted` state for downstream QA.

#### `qa_review_node`
Runs QA in parallel for all prerequisite-ready sections that have content (skips elements not yet generated). Applies results to each element and sets `current_element_index` to the first reviewed section.

**Configuration Constants** (in `src/nodes/qa_review_node.py`):
- `QA_PASS_THRESHOLD = 0.8` — Minimum confidence to pass QA
- `QA_REWRITE_THRESHOLD = 0.5` — Below this triggers automatic rewrite
- `QA_CONCURRENCY_LIMIT = 4` — Max parallel LLM calls

**Threshold Enforcement:**
The node enforces these thresholds deterministically, overriding LLM's `overall_passes` when:
- Any critical requirement failed → `passes = False, needs_rewrite = True`
- `overall_confidence < QA_PASS_THRESHOLD` → `passes = False`
- `overall_confidence < QA_REWRITE_THRESHOLD` → `needs_rewrite = True`

**Caching:**
QA is skipped for elements where:
- Content hash matches `last_qa_content_hash`
- Previous QA passed

**Concurrency:**
Parallel QA limited to `QA_CONCURRENCY_LIMIT = 4` concurrent LLM calls via semaphore.

**State Invariant**: Every element with `status` in `("qa_passed", "needs_revision")` MUST have `qa_review != None`. The node calls `element.apply_qa_review()` for ALL paths, including early returns when no requirements exist.

Approval prompts now display the **full draft content** before asking for user approval, not just QA feedback.

#### `handle_draft_response_node`
Processes user approval/rejection/revision request.

#### `advance_to_next_element_node`
Moves to next draft element or routes to finalize.

### Phase 5: Review

#### `finalize_node`
Presents complete document for final review.

#### `handle_element_revision_request`
Processes late element revision requests during review phase.

### Phase 6: Complete

#### `end_conversation_node`
Handles conversation termination with write-another prompt.

#### `handle_write_another_node`
Handles "write another PD?" response using **structured intent classification**.

Uses LLM's structured `IntentClassification` (not heuristic message parsing):
- `confirm` intent → restart session (`wants_another=True`)
- `reject` intent → end session (`wants_another=False`)
- Other intents → ask for clarification

#### `export_document_node`
Exports position description to chosen format (Markdown or Word).

Routes to `end_conversation` on success (which asks "write another?").
Does NOT ask "write another?" directly — that's delegated to `end_conversation_node`.

---

## Routing Functions

Located in `routing.py` (10 functions exported):

```python
def route_by_intent(state: AgentState) -> RouteDestination:
    """Main routing based on classified intent and current phase."""
    
def route_after_init(state: AgentState) -> RouteDestination:
    """Route after initialization."""

def route_after_qa(state: AgentState) -> RouteDestination:
    """Route based on QA pass/fail."""

def route_after_draft_response(state: AgentState) -> RouteDestination:
    """Route after user feedback on draft."""

def route_after_advance_element(state: AgentState) -> RouteDestination:
    """Route to next element or finalize."""

def route_after_finalize(state: AgentState) -> RouteDestination:
    """Route after finalize (to user_input for response)."""

def route_after_element_revision(state: AgentState) -> RouteDestination:
    """Route after late revision request."""

def route_after_export(state: AgentState) -> RouteDestination:
    """Route after export (to user_input for 'write another?' response)."""
    
def route_should_end(state: AgentState) -> bool:
    """Check if conversation should end."""
```

---

## Node Pattern

Nodes return either:

1. **Dict** - Simple state updates (LangGraph determines next node via edges)
```python
def my_node(state: AgentState) -> dict:
    return {"key": "value", "messages": [AIMessage(content="...")]}
```

2. **Command** - Explicit routing (for conditional flows)
```python
from langgraph.types import Command

def my_node(state: AgentState) -> Command:
    return Command(update={"key": "value"}, goto="next_node")
```

---

## Adding a New Node

1. Create `src/nodes/<name>_node.py`
2. Define async function accepting `AgentState`, returning dict or `Command`
3. Export from `src/nodes/__init__.py`
4. Add to graph in `src/graphs/main_graph.py`
5. Create test in `tests/test_node_<name>.py`
6. Update this doc

---

## Testing

```bash
# All node tests
poetry run pytest tests/test_node_*.py tests/test_unit_nodes.py -v

# Specific node
poetry run pytest tests/test_node_init.py -v
```
