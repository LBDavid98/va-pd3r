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

## ⛔ NO HEURISTIC DECISION MAKING ⛔
```markdown
This project does NOT permit heuristic decision making in src/.

FORBIDDEN (see ADR-007):
- Keyword matching to identify user intent or targets
- If/else chains to interpret ambiguous user input
- Pattern matching for content evaluation (QA, validation)
- Dict lookups to map user words to internal names

ALLOWED (data processing, not decisions):
- Format validation: regex for series codes, grade ranges
- Data parsing: extracting numbers, splitting strings
- Explicit command parsing: UI button responses

REQUIRED:
- User intent interpretation → LLM
- Element/section identification → LLM  
- Content quality evaluation → LLM
- Any ambiguity resolution → LLM

See: docs/decisions/007-no-heuristic-decisions.md
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

## Quick Start
- Install dependencies: `poetry install`
- Run agent: `poetry run python -m src.main`
- Run with tracing: `PD3R_TRACING=true poetry run python -m src.main`
- Analyze trace: `poetry run python scripts/analyze_trace.py --trace output/logs/<trace>.jsonl`
- Tests: `poetry run pytest -q`

## Current Focus (2026-03-03)
```markdown
TECH DEBT REMEDIATION → CONTAINERIZATION → UX

Phase 1 (in progress): Technical debt cleanup
- Deprecated code removed, imports consolidated to src/config/
- Async patterns standardized via src/utils/async_compat.py
- State compaction wired into graph transitions
- Hallucination guards added to RAG/QA prompts

Phase 2 (next): FastAPI + WebSocket API layer, Docker containerization
Phase 3: React UX with chat panel + product panel

See: docs/plans/mvp_roadmap.md
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

## E2E & Scripted Testing
```markdown
For automated conversation testing, use the patterns in scripts/run_e2e_test.py.

REFERENCE IMPLEMENTATION: scripts/run_e2e_test.py
- Uses graph.astream() with proper async handling
- Handles interrupts via graph.aget_state() checking for interrupt values
- Resumes with Command(resume=user_input)
- Uses proper tracing via start_run_trace() and save_trace_log()

RUNNING E2E TESTS:
  poetry run python scripts/run_e2e_test.py           # minimal interview
  poetry run python scripts/run_e2e_test.py --full    # full interview
  poetry run python scripts/run_e2e_test.py --trace   # with tracing
  poetry run python scripts/run_e2e_test.py -v        # verbose output

RUNNING QUESTION ANSWERING TESTS:
  poetry run python scripts/test_question_answering.py --trace -v

CREATING NEW TEST SCRIPTS:
When creating new scripted test runners:
1. Copy the pattern from run_e2e_test.py (NOT agentscript)
2. Use asyncio.run() with an async main function
3. Use graph.astream() for execution, graph.aget_state() for interrupts
4. Handle telemetry errors gracefully (chromadb telemetry noise is expected)
5. Always use Command(resume=...) to send user input after interrupts

ANALYZING RESULTS:
  poetry run anode full -n 1 -v             # Full graph LLM analysis of last 1 run
  poetry run anode <node_name> -n 3         # Analyze specific node from last 3 runs  
  poetry run anode --list                   # List all available nodes
  poetry run anode --costs -n 5             # Show cost breakdown for last 5 runs
  poetry run anode full --raw               # Raw metrics without LLM analysis
  poetry run python scripts/analyze_trace.py <trace>  # Legacy summary report

Note: anode uses `-n` to specify HOW MANY recent trace files to analyze (not a trace path).
      Output is auto-saved to output/analysis/anode_<node>_<timestamp>.md

DO NOT use agentscript for new test development—it has async/telemetry issues.
Use the Python script pattern instead.
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

### Testing with VCR Cassettes

```markdown
LLM integration tests use VCR.py to record and replay API responses.

HOW IT WORKS:
1. First run: Real API call → response saved to tests/cassettes/*.yaml
2. Later runs: Replay saved response → no API call, deterministic, free

BENEFITS:
- Tests real LLM behavior (not developer-invented mocks)
- Deterministic: same response every run
- Fast: no network latency
- Free: no API costs after recording

COMMANDS:
- Run all tests: `poetry run pytest tests/`
- Re-record cassettes: `poetry run pytest --vcr-record=all tests/`
- Record only new: `poetry run pytest --vcr-record=new_episodes tests/`

MARKING TESTS:
- `@pytest.mark.vcr` - uses cassette recording
- `@skip_without_llm` - skips if no API key (for tests not yet recorded)

See: docs/decisions/008-vcr-testing.md (TODO: create when implementing)
```

Tracing & LLM Analysis
- Enable `LOCAL_TRACING=true` to write traces to `output/logs/` (JSONL + `_readable.log`).
- Traces include `llm_call` events with token counts and cost estimates.

Testing
- Use `pytest` (+ `pytest-asyncio` for async tests).
- Integration tests may require `.env` API keys; see `.env.example`.

Where to go next
- Read [docs/INDEX.md](docs/INDEX.md) for procedures and module docs.
- Inspect [pyproject.toml](pyproject.toml) for CLI script configuration.
