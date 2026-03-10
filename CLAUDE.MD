# Project Context

**PD3r (Pete)** is a chat agent that writes federal position descriptions using LangGraph and Pydantic v2. See [README.md](README.md) for schemas and API details.

The OPENAI API KEY is always in the .env folder, use poetry to run things and make sure you assume the API key is there.
## ⛔ NO MOCK LLM POLICY ⛔
```markdown
This project does NOT permit mock/fallback LLM implementations in src/.

FORBIDDEN:
- Pattern-matching fallbacks that bypass LLM calls
- "Basic" classification functions as alternatives to LLM
- try/except blocks that silently fall back to non-LLM code
- Environment flags that toggle between mock and real LLM

REQUIRED:
- Every node that needs LLM MUST call the real LLM
- Missing API key = ConfigurationError (fail fast)
- Tests use VCR cassettes of real LLM responses, NOT mocks

WHY:
- Mock implementations create false confidence in tests
- Prompt bugs go undetected when bypassing LLM
- Dual code paths diverge over time and create bugs
- Production behavior differs from test behavior

See: docs/modules/nodes.md, docs/decisions/005-no-mock-llm.md
```

## ⛔ NO HEURISTIC ROUTING POLICY ⛔
```markdown
This project does NOT permit heuristic/if-else routing in src/.

FORBIDDEN (see ADR-006):
- If/else routing based on phase: `if phase == "interview": return _route_interview_phase()`
- If/else routing based on intent labels: `if intent == "provide_information": return "map_answers"`
- Manual phase state management: `state["phase"] = "drafting"`
- Routing functions that don't call LLM: `def route_by_intent(state): ...`
- Conditional edges with >3 explicit routes (sign of heuristic routing)

REQUIRED:
- LLM decides next action via tool selection (ReAct pattern)
- Human interactions use `interrupt()` and `Command(resume=...)`
- Use `create_react_agent` for simple agents
- Use `create_supervisor` for multi-agent coordination
- Routing complexity lives in tool descriptions, not Python code

WHY:
- Heuristic routing discards LLM reasoning
- Creates brittle, hard-to-maintain code (see: 474-line routing.py)
- Violates LangGraph best practices
- Causes test/production divergence

ALLOWED EXCEPTIONS:
- Error handling routes (e.g., missing API key → error node)
- Simple binary conditions (e.g., `should_end` → END)

See: docs/decisions/006-llm-driven-routing.md, docs/plans/langgraph_migration_plan.md
```

## ⛔ NO GOD METHODS POLICY ⛔
```markdown
FORBIDDEN:
- API endpoint handlers >50 lines (extract to helper methods/classes)
- Methods mixing orchestration with business logic
- Inline data transformations in streaming loops (extract to transforms module)
- Duplicate transformation logic (same data → same shape in multiple places)

REQUIRED:
- API methods orchestrate: validate, delegate, return
- Business logic lives in dedicated modules (transforms, trackers, etc.)
- Single source of truth for data transformations

See: docs/decisions/009-send-message-decomposition.md
```

## ⛔ NO OPTIMISTIC STATUS POLICY ⛔
```markdown
FORBIDDEN:
- Frontend setting element status (approved, needs_revision, etc.) before backend confirms
- Sending free-text strings ("approve") for structured actions that have dedicated protocols
- Frontend and backend independently deciding element status

REQUIRED:
- Element status changes flow: frontend sends intent → backend processes → backend sends element_update → frontend renders
- Structured actions (approve, reject, regenerate) use element_action WebSocket protocol
- Frontend may show pending/loading state while waiting for backend confirmation

See: docs/decisions/010-backend-authoritative-status.md
```

## ⛔ NO MESSAGE SUPPRESSION FOR STATE POLICY ⛔
```markdown
FORBIDDEN:
- Regex-based classification to hide agent state from the user
- Suppressing agent prompts/questions (user must see what agent is asking)
- Using chat messages as the transport for internal pipeline state

REQUIRED:
- Agent internal state communicated via structured activity_update messages
- Chat messages are conversational (user-facing questions, answers, confirmations)
- Activity indicators in UI show current agent operation
- Minimal suppression only for content already shown elsewhere (e.g., draft text in panel)

See: docs/decisions/011-structured-agent-visibility.md
```

## Quick Start
- Install dependencies: `poetry install`
- Run agent: `poetry run python -m src.main`
- Run with tracing: `PD3R_TRACING=true poetry run python -m src.main`
- Analyze trace: `poetry run python scripts/analyze_trace.py --trace output/logs/<trace>.jsonl`
- Tests: `poetry run pytest -q`

## Current Focus (2026-03-10)
```markdown
ARCHITECTURAL REMEDIATION COMPLETE → HANDOFF PREP

Completed:
- Phase 1-4 of MVP roadmap (tech debt, API, UX, polish)
- Architectural remediation (Phases 1-4):
  - send_message() decomposed into orchestration + helpers (Phase 1)
  - Backend-authoritative element status with element_action protocol (Phase 2)
  - Structured activity_update visibility replacing message suppression (Phase 3)
  - Dead batch/parallel code removed (Phase 4)
- 899+ tests passing, TypeScript clean

See: docs/plans/mvp_roadmap.md, docs/plans/architectural_remediation.md
```

## Testing Phase Controls
```markdown
Environment variables to control test execution:

- `PD3R_STOP_AT=interview` - Stop after interview complete, skip drafting
- `PD3R_STOP_AT=requirements` - Stop after requirements confirmed
- `PD3R_SKIP_QA=true` - Skip QA review during drafting (future use)

Run with controls:
  PD3R_STOP_AT=interview PD3R_TRACING=true poetry run python -m src.main
```

## Documentation Reading Order
```markdown
1. ALWAYS read: `AGENTS.MD` (this file)
2. For context: `docs/INDEX.md` → relevant section indexes
2.1 Use get_langgraph_documentation MCP .vscode/mcp.json is a core resource for ensure best design patterns when designing. 
3. On demand: Specific docs as needed for current task
4. Never read all docs upfront—use indexes to navigate
5. Search the web for complex integration issues if your first attempt doesn't produce a clear next step.
6. Before writing a document, review the document standards.
```

## LangGraph Knowledge Base
```markdown
For ANY task involving nodes, prompts, edges, graphs, or LangGraph design/implementation:
- LangGraph is our GOLD STANDARD for agent architecture
- Use the LangGraph MCP server (configured in .vscode/mcp.json) to query official docs
- Search LangGraph docs BEFORE implementing nodes, edges, or graph patterns
- Consult LangGraph examples for best practices on:
  - StateGraph construction and node definition
  - Conditional edges and routing logic
  - Checkpointing and persistence patterns
  - Streaming and callbacks
  - Tool integration and structured outputs
- When in doubt about LangGraph patterns, query the docs rather than guessing
```

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
□ Update punch list notes after completing each step
```

## After Each Change
```markdown
□ Run unit tests: pytest tests/
□ All pass? → Prompt for commit
□ Any fail? → Fix new code (not tests)
□ Update docs if behavior changed
□ Log session outputs
```

## Red Flags (STOP and Discuss)
```markdown
⚠ Change requires modifying >3 files
⚠ Test expects different behavior than code provides
⚠ Undocumented function being modified
⚠ No tests exist for affected code
⚠ Change affects data models/schemas
```
## Code Standards

### Core Principles

```markdown
- Python 3.11+ with type annotations on all functions
- Async-first: `async/await` for I/O, `httpx` for HTTP (never `requests`)
- Pydantic v2 models for data structures, API responses, and LLM structured outputs
- Custom exceptions in dedicated module; exponential backoff for external APIs
- All prompts must be defined in `src/prompts/`; nodes import prompts, never define inline
```

## Debugging & Error Logs
- **API errors**: `output/logs/api.log` (WARNING+, rotated at 5MB × 3 backups)
- **Trace logs**: `output/logs/{timestamp}_{run_id}_readable.log` (requires `PD3R_TRACING=true`)
- **Frontend errors**: Browser console + sonner toast notifications in UI
- **WebSocket errors**: Logged server-side to api.log, shown client-side as toast + chat message

Tracing & LLM Analysis
- Enable `LOCAL_TRACING=true` to write traces to `output/logs/` (JSONL + `_readable.log`).
- Traces include `llm_call` events with token counts and cost estimates.

Testing
- Use `pytest` (+ `pytest-asyncio` for async tests).
- Integration tests may require `.env` API keys; see `.env.example`.

Where to go next
- Read [docs/INDEX.md](docs/INDEX.md) for procedures and module docs.
- Inspect [pyproject.toml](pyproject.toml) for CLI script configuration.
