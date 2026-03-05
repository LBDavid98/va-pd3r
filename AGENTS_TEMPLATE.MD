A template for AI-assisted agent development projects. 

---

## Project Context

```markdown
[PROJECT_NAME] is a Python AI assistant using [LLM_PROVIDER] APIs, Pydantic v2, and [ORCHESTRATION_FRAMEWORK].

See `README.md` for schemas and API details.
```

---

## Critical Rules

```markdown
- DO NOT modify data models without explicit direction. All code must reflect Pydantic models.
- DO NOT edit PLAN or SCHEMA MD files without explicit instructions.
- ALWAYS update the PUNCH_LIST and ensure README.MD accurately reflects current structure.
- Tests define intended behavior—code adapts to tests, never the reverse.
```

---

## Documentation Reading Order

```markdown
1. ALWAYS read: `AGENTS.MD` (this file)
2. For context: `docs/INDEX.md` → relevant section indexes
3. On demand: Specific docs as needed for current task
4. Never read all docs upfront—use indexes to navigate
5. Search the web for complex integration issues if your first attempt doesn't produce a clear next step.
```

---

## Mandatory Elements for Coding Tasks

```markdown
Every coding task requires these steps (scale effort to complexity):

1. **Understand** (Analysis/Requirements): Define goals, inputs, outputs, constraints; ask clarifying questions.
2. **Plan & Design** (Decomposition): Break into sub-problems; outline logic with pseudocode; identify dependencies.
3. **Develop** (Coding): Translate design into clean, modular code.
4. **Test** (Verification): Write and run unit tests; debug failures.
5. **Document** (Maintain): Add comments, update documentation, plan for future updates.

NOTE: For complex implementations, use and update a punch_list even if one doesn't exist yet.
Delete task-specific punch lists when complete.
```

---

## Before Starting Any Task

```markdown
□ Read AGENTS.MD
□ Read docs/INDEX.md
□ Identify affected modules
□ Read relevant module docs
□ Check for existing tests
```

## During Implementation

```markdown
□ Document before/while coding (not after)
□ Test each function immediately
□ Recommend commit after each logical unit success
□ Capture decisions as they're made
□ Prompt human at decision points
```

## After Each Change

```markdown
□ Run unit tests: pytest tests/
□ All pass? → Prompt for commit
□ Any fail? → Fix new code (not tests)
□ Update docs if behavior changed
□ Log session outputs
```

---

## Red Flags (STOP and Discuss)

```markdown
⚠ Change requires modifying >3 files
⚠ Test expects different behavior than code provides
⚠ Undocumented function being modified
⚠ No tests exist for affected code
⚠ Change affects data models/schemas
```

---

## Code Standards

### Core Principles

```markdown
- Python 3.11+ with type annotations on all functions
- Async-first: `async/await` for I/O, `httpx` for HTTP (never `requests`)
- Pydantic v2 models for data structures, API responses, and LLM structured outputs
- Custom exceptions in dedicated module; exponential backoff for external APIs
- All prompts must be defined in `src/prompts/`; nodes import prompts, never define inline
```

### State vs Models (for LangGraph projects)

```markdown
- **LangGraph state**: Use `TypedDict` (performance and reducer compatibility)
- **Everything else**: Use Pydantic `BaseModel` (data models, API responses, structured outputs)

Example:
```python
from typing import Annotated, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_input: str
    result: Optional[dict]  # Pydantic model serialized as dict
```
```

### Node Pattern (for graph-based projects)

```markdown
Nodes return `Command` objects for explicit routing:

```python
from typing import Literal
from langgraph.types import Command

# Define all possible destinations as a type
NODE_DESTINATIONS = Literal["next_node", "error_node", "end"]

async def my_node(state: AgentState) -> Command[NODE_DESTINATIONS]:
    """
    PURPOSE: Brief description of what this node does.
    DEPENDENCIES: List key imports.
    STATE: What it reads and writes.
    """
    # Node logic here
    return Command(update={"key": "value"}, goto="next_node")
```

This pattern:
- Makes routing explicit and traceable
- Enables automatic graph visualization
- Provides type safety for destinations
```

### Prompt Templating

```markdown
Use Jinja2 templates in `src/prompts/templates/`:

```jinja2
{# src/prompts/templates/analyze.jinja #}
You are analyzing a user request.

USER INPUT:
{{ user_input }}

CONTEXT:
{{ context | tojson(indent=2) }}

Provide your analysis as structured JSON.
```

Load and render in code:
```python
from src.prompts import get_template

template = get_template("analyze.jinja")
prompt = template.render(user_input=state["user_input"], context=context)
```
```

---

## Testing Standards

```markdown
- pytest with pytest-asyncio for async tests
- DO NOT MOCK LLM CALLS—use real calls or skip with markers
- All tests in `/tests`, named `test_unit_*.py` or `test_integration_*.py`
- Tests define behavior—implementation conforms to tests
- Unit tests should load `.env` if they need API keys
```

### Test Structure

```markdown
tests/
├── conftest.py              # Shared fixtures
├── test_unit_models.py      # Pydantic model validation
├── test_unit_nodes.py       # Node logic (mock external services)
├── test_unit_tools.py       # Tool implementations
├── test_integration_*.py    # Full flow tests (require API keys)
```

---

## Documentation Structure

```markdown
docs/
├── INDEX.md                 # Navigation hub (read second after AGENTS.MD)
├── modules/                 # Module-specific reference docs
│   ├── INDEX.md             # Module navigation
│   ├── nodes.md             # Node reference with line numbers
│   ├── models.md            # Pydantic model reference
│   └── [module].md          # Per-module documentation
├── procedures/              # How-to guides
│   ├── testing.md
│   ├── new-node.md
│   └── debugging.md
├── decisions/               # Architecture Decision Records
│   └── INDEX.md
└── plans/                   # Implementation plans (archive when complete)
    └── archives/
```

### Module Doc Template

```markdown
# [Module] Reference

> **Last Updated**: [Date]
> **Module Path**: `src/[module]/`
> **Lines of Code**: ~[X] across [N] files

---

## Overview

[What this module does and why it exists]

## Module Structure

| File | Purpose | Lines |
|------|---------|-------|
| `__init__.py` | Exports | L1-50 |
| `main.py` | Core logic | L1-200 |

## Key Functions

### `function_name()`
**File**: [file.py](../../src/module/file.py) (Lines X-Y)

[Description, parameters, return value]

## Testing

```bash
poetry run pytest tests/test_unit_[module].py -v
```
```

---

## Commit Discipline

```markdown
- Prompt for commit after each logical change
- Use format: `<type>(<scope>): <subject>`
- Include WHY/WHAT/HOW/RISK in body for non-trivial changes
- Never batch unrelated changes
- Maximum 30 minutes between commit prompts

Types: feat, fix, docs, refactor, test, chore
```

---

## Project Structure Template

```markdown
project/
├── AGENTS.MD                # AI agent instructions (this file)
├── README.md                # Project documentation
├── pyproject.toml           # Dependencies (Poetry)
├── .env.example             # Environment template
├── .env                     # Local secrets (git-ignored)
│
├── src/
│   ├── __init__.py
│   ├── main.py              # Entry point
│   ├── graphs/              # Workflow definitions
│   ├── nodes/               # Node implementations
│   ├── models/              # Pydantic models
│   ├── tools/               # Tool implementations
│   ├── prompts/             # Jinja2 templates
│   │   └── templates/
│   └── [domain]/            # Domain-specific modules
│
├── tests/
│   ├── conftest.py
│   ├── test_unit_*.py
│   └── test_integration_*.py
│
├── docs/
│   ├── INDEX.md
│   ├── modules/
│   ├── procedures/
│   └── decisions/
│
└── output/                  # Runtime outputs (git-ignored except .gitkeep)
    └── logs/
```

---

## Scaling Guidelines

### Simple Project (< 500 LOC)

```markdown
- AGENTS.MD + README.md sufficient
- Single `src/` with flat structure
- `tests/test_*.py` without subdirectories
- Skip `docs/` hierarchy—use README sections
```

### Medium Project (500-3000 LOC)

```markdown
- AGENTS.MD + README.md + docs/INDEX.md
- Organize `src/` by domain
- Separate unit/integration tests
- Module docs for complex areas only
```

### Large Project (3000+ LOC)

```markdown
- Full documentation structure
- Punch lists for multi-day features
- Architecture Decision Records
- Tracing/debugging infrastructure
- Performance testing plan
```

---

## Tips for AI Collaboration

### Stay In Scope

```markdown
- Only modify files directly related to the current request
- Do not refactor or "improve" code outside the request
- Do not add features or abstractions not explicitly requested
- When fixing a bug, fix that bug—do not refactor surrounding code
```

### Avoid Over-Engineering

```markdown
- Prefer simple, direct solutions over elaborate abstractions
- Do not add layers of indirection "for future flexibility"
- If a function does the job, do not wrap it in a class
- Match solution complexity to problem complexity
```

### Test Integrity

```markdown
- Never modify production code solely to make tests pass
- If tests fail, verify test expectations are correct first
- Fix implementation to match intended behavior, not the reverse
- Tests validate behavior—do not warp behavior to validate tests
```

### Prevent Cascading Changes

```markdown
- Scope changes to the smallest possible surface area
- If a change requires modifying many files, stop and discuss
- Preserve existing interfaces; extend rather than modify when possible
```

---

## Quick Reference Card

```markdown
┌─────────────────────────────────────────────────────────────┐
│ BEFORE: Read AGENTS.MD → docs/INDEX.md → module docs       │
├─────────────────────────────────────────────────────────────┤
│ DURING: Document → Code → Test → Commit prompt             │
├─────────────────────────────────────────────────────────────┤
│ AFTER:  pytest → All pass? Commit. Fail? Fix new code.     │
├─────────────────────────────────────────────────────────────┤
│ ALWAYS: Pydantic models define truth. Tests define intent. │
└─────────────────────────────────────────────────────────────┘
```

---

## Customization Notes

```markdown
Remove or adapt sections based on your project:

- [ ] No LangGraph? Remove State vs Models, Node Pattern sections
- [ ] No Azure? Adapt storage references
- [ ] Simple CLI tool? Use "Simple Project" structure
- [ ] No LLM calls? Remove "DO NOT MOCK LLM" rule
- [ ] Team project? Add PR review guidelines

The core principles that transfer to any project:
1. Models define data contracts
2. Tests define intended behavior  
3. Documentation enables AI collaboration
4. Small, focused changes prevent cascading failures
5. Explicit routing/flow beats implicit magic
```

---

## Dependencies & CLI (Poetry)

```markdown
- Use Poetry for dependency and environment management.
- Install dependencies: `poetry install`
- Add a console script in `pyproject.toml` for easy CLI runs:

    [tool.poetry.scripts]
    shade-agent = "src.main:main"

- Run the agent locally:
    - Development: `poetry run python -m src.main`
    - With tracing: `LOCAL_TRACING=true poetry run python -m src.main --trace`
    - Run tests: `poetry run pytest -q`

Note: Prefer `poetry run` which uses the virtualenv Poetry manages.
```

## Local Tracing & LLM Analysis

```markdown
- Enable local tracing with `LOCAL_TRACING=true` in `.env` or as an env var.
- Traces are written to `output/logs/` as JSONL and a human-readable `_readable.log`.
- Quick analysis:

    `poetry run python scripts/analyze_trace.py --trace output/logs/<trace>.jsonl`

- For node-level deep dives or LLM cost analysis, use `scripts/analyze_trace.py` flags (see script help).
- Ensure traces capture `llm_call` events; they include `model`, `prompt_tokens`, `completion_tokens`, and `cost_usd`.
- Use traces for:
    - debugging node routing and state transitions
    - measuring LLM usage and estimating costs
    - comparing runs and regressions
```

---

## Minimal `AGENTS.MD` Example

The following is the actual `AGENTS.MD` used by PD3r (Pete):

```markdown
# Project Context

**PD3r (Pete)** is a chat agent that writes federal position descriptions using LangGraph and Pydantic v2. See [README.md](README.md) for schemas and API details.

## Quick Start
- Install dependencies: `poetry install`
- Run agent: `poetry run python -m src.main`
- Run with tracing: `LOCAL_TRACING=true poetry run python -m src.main --trace`
- Analyze trace: `poetry run python scripts/analyze_trace.py --trace output/logs/<trace>.jsonl`
- Tests: `poetry run pytest -q`


## Documentation Reading Order
1. ALWAYS read: `AGENTS.MD` (this file)
2. For context: `docs/INDEX.md` → relevant section indexes
3. On demand: Specific docs as needed for current task
4. Never read all docs upfront—use indexes to navigate
5. Search the web for complex integration issues if your first attempt doesn't produce a clear next step.

## Mandatory Elements for Coding Tasks
Every coding task requires these steps (scale effort to complexity):

1. **Understand** (Analysis/Requirements): Define goals, inputs, outputs, constraints; ask clarifying questions.
2. **Plan & Design** (Decomposition): Break into sub-problems; outline logic with pseudocode; identify dependencies.
3. **Develop** (Coding): Translate design into clean, modular code.
4. **Test** (Verification): Write and run unit tests; debug failures.
5. **Document** (Maintain): Add comments, update documentation, plan for future updates.

NOTE: For complex implementations, use and update a punch_list even if one doesn't exist yet.
Delete task-specific punch lists when complete.

## Before Starting Any Task
□ Read AGENTS.MD
□ Read docs/INDEX.md
□ Identify affected modules
□ Read relevant module docs
□ Check for existing tests

## During Implementation
□ Document before/while coding (not after)
□ Test each function immediately
□ Recommend commit after each logical unit success
□ Capture decisions as they're made
□ Prompt human at decision points

## After Each Change
□ Run unit tests: pytest tests/
□ All pass? → Prompt for commit
□ Any fail? → Fix new code (not tests)
□ Update docs if behavior changed
□ Log session outputs

## Red Flags (STOP and Discuss)
⚠ Change requires modifying >3 files
⚠ Test expects different behavior than code provides
⚠ Undocumented function being modified
⚠ No tests exist for affected code
⚠ Change affects data models/schemas

## Code Standards

### Core Principles
- Python 3.11+ with type annotations on all functions
- Async-first: `async/await` for I/O, `httpx` for HTTP (never `requests`)
- Pydantic v2 models for data structures, API responses, and LLM structured outputs
- Custom exceptions in dedicated module; exponential backoff for external APIs
- All prompts must be defined in `src/prompts/`; nodes import prompts, never define inline

Tracing & LLM Analysis
- Enable `LOCAL_TRACING=true` to write traces to `output/logs/` (JSONL + `_readable.log`).
- Traces include `llm_call` events with token counts and cost estimates.

Testing
- Use `pytest` (+ `pytest-asyncio` for async tests).
- Integration tests may require `.env` API keys; see `.env.example`.

Where to go next
- Read [docs/INDEX.md](docs/INDEX.md) for procedures and module docs.
- Inspect [pyproject.toml](pyproject.toml) for CLI script configuration.
```

---

## Graph Visualization

PD3r auto-exports the workflow graph to `output/graph.png` after every build/test run. The PNG includes a timestamp in the top-right corner and is overwritten each run.

See `src/graphs/export.py` for implementation and `docs/procedures/graph-export.md` for details.