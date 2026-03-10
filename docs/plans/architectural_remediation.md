# Architectural Remediation Plan

**Created:** 2026-03-10
**Status:** Draft
**Scope:** Address 4 systemic architectural problems while preserving 100% of existing functionality

---

## Problem Statement

Four architectural problems compound each other:

| # | Problem | Root Cause | Symptom |
|---|---------|-----------|---------|
| 1 | **`send_message()` god method** (173 lines) | Mixes graph orchestration, message streaming, element change detection, QA transformation, and state extraction in one scope | Shadowing bugs, untestable logic, change in one concern breaks others |
| 2 | **Competing control flows** | Frontend optimistically sets `status: "approved"` + `locked: true`, then sends `"approve"` as text for LLM classification | If backend disagrees (e.g., routes to reprompt instead of approve), states diverge silently |
| 3 | **Message suppression hides agent state** | `classifyAgentMessage()` (138 lines of regex) suppresses prompts like "Do you approve this section?" | User has zero visibility when the agent is confused or looping; debugging requires backend logs |
| 4 | **Sequential flow with parallel infrastructure** | Graph processes elements one at a time, but element streaming, batch QA, and pre-population logic add complexity for parallel-like behavior | Over-engineering for current flow; snapshot/hash comparison (fragile `len + [:50]`) exists only because of this complexity |

### How They Compound

- Problem 1 (god method) makes Problem 2 (competing flows) hard to diagnose — the approve path is buried in 173 lines of mixed concerns.
- Problem 3 (suppression) masks Problem 2 — when approve/backend disagree, the user never sees the agent's confused response.
- Problem 4 (parallel infra) inflates Problem 1 — element snapshot tracking, hash comparison, and QA transformation exist in `send_message()` solely to support streaming change detection.

---

## Guiding Principles

1. **Preserve all user-facing behavior** — every feature works identically after each phase
2. **One concern per unit** — each function/class has one reason to change
3. **Backend is authoritative** — frontend never sets status; it sends intent, backend confirms
4. **Transparency over suppression** — agent state is visible to the user through structured UI, not hidden by regex
5. **Test at boundaries** — each extracted module gets its own tests before integration
6. **Incremental delivery** — each phase produces a working system; no "big bang" rewrite

---

## Phase 1: Decompose `send_message()` (Backend)

**Goal:** Break the 173-line monolith into single-responsibility units that can be tested, modified, and reasoned about independently.

### 1.1 Extract QA Transformation

**Files changed:** `src/api/session_manager.py`, new `src/api/transforms.py`
**Lines affected:** session_manager.py:389-409 (streaming), session_manager.py:532-550 (REST)

**What:**
- Create `src/api/transforms.py` with a single function:
  ```python
  def qa_review_to_summary(raw_qa: dict | object) -> dict | None
  ```
- This function handles both code paths:
  - **Streaming path** (line 389-409): receives `raw_qa` as a `dict` from graph event
  - **REST path** (line 532-550): receives `raw_qa` as a Pydantic model (`QAReview`) from `DraftElement.model_validate()`
- Replace both inline transformations with a call to this function

**Dependencies:**
- `src/models/draft.py` — `QAReview` model (read-only, no changes needed)
- `src/api/session_manager.py` — both call sites import from new module

**Test plan:**
- Unit test `qa_review_to_summary()` with: dict input, Pydantic model input, None input, empty checks, missing keys
- Verify REST endpoint `GET /sessions/{id}/draft` returns identical shape before/after
- Verify WebSocket `element_update` messages have identical shape before/after

**Anticipated effects:**
- No behavioral change — pure extraction
- If a QA field name changes in the model, it now breaks in one place instead of two

### 1.2 Extract Element Change Detector

**Files changed:** `src/api/session_manager.py`, new `src/api/element_tracker.py`
**Lines affected:** session_manager.py:333-416

**What:**
- Create `ElementChangeTracker` class:
  ```python
  class ElementChangeTracker:
      def __init__(self, initial_elements: list[dict])
      def detect_changes(self, current_elements: list[dict]) -> list[ElementChange]
  ```
- `ElementChange` is a dataclass: `name, status, display_name, content (optional), qa_summary (optional)`
- Replace the fragile hash (`len + [:50]`) with `hashlib.sha256(content.encode()).hexdigest()[:16]`
- Move "drafted → status-only update" logic into `detect_changes()` return value (content=None for pre-QA)
- Uses `qa_review_to_summary()` from step 1.1

**Dependencies:**
- `src/api/transforms.py` (from 1.1)
- `src/api/session_manager.py` — single call site in `send_message()`

**Test plan:**
- Unit test: no changes → empty list
- Unit test: status change → returns change with old/new status
- Unit test: content change → returns change with content
- Unit test: "drafted" status → returns change without content
- Unit test: QA data present → qa_summary populated
- Integration: WebSocket `element_update` messages identical before/after

**Anticipated effects:**
- Fixes the fragile hash comparison (content changes beyond 50 chars now detected)
- No behavioral change for normal flows

### 1.3 Extract Streaming Orchestrator

**Files changed:** `src/api/session_manager.py`
**Lines affected:** session_manager.py:275-448 (entire `send_message()`)

**What:**
- Refactor `send_message()` into orchestration calls:
  ```python
  async def send_message(self, session_id, content, field_overrides, on_message, on_state, on_element_update):
      self._validate_session(session_id)
      config = self._config_for(session_id)

      if field_overrides:
          await self._apply_field_overrides(config, field_overrides)

      pre_state = await self._graph.aget_state(config)
      tracker = ElementChangeTracker(pre_state.values.get("draft_elements", []))
      msg_counter = MessageCounter(pre_state.values.get("messages", []))

      result = await self._stream_graph(
          config, content, tracker, msg_counter,
          on_message, on_state, on_element_update,
      )

      await self._update_position_title(session_id, result)
      interrupt_data = await self._get_interrupt(config)

      return {
          "messages": msg_counter.unstreamed_messages(result),
          "state": self._extract_state(session_id, result),
          "interrupt": interrupt_data,
      }
  ```
- Extract `_stream_graph()` as a private method (lines 345-416): graph streaming loop only
- Extract `MessageCounter` helper (or keep as simple closure) for message dedup tracking
- Tracing stays in `send_message()` via existing try/finally

**Dependencies:**
- `ElementChangeTracker` (from 1.2)
- `qa_review_to_summary` (from 1.1, used by tracker)
- All existing callbacks (no signature change)

**Test plan:**
- `send_message()` return value shape unchanged
- WebSocket integration: full message flow identical
- REST fallback: `POST /sessions/{id}/message` still works
- Tracing: trace logs still generated with `PD3R_TRACING=true`

**Anticipated effects:**
- `send_message()` drops from ~173 lines to ~30 lines of orchestration
- Each extracted unit is independently testable
- No callback signature changes — websocket.py untouched

### Phase 1 Punch List

- [x] 1.1a Create `src/api/transforms.py` with `qa_review_to_summary()`
- [x] 1.1b Write unit tests for `qa_review_to_summary()` — 8 tests passing
- [x] 1.1c Replace streaming QA transform (session_manager.py) with function call
- [x] 1.1d Replace REST QA transform (session_manager.py) with function call
- [x] 1.1e Run full test suite — 881 passed
- [x] 1.2a Create `src/api/element_tracker.py` with `ElementChangeTracker`
- [x] 1.2b Write unit tests for `ElementChangeTracker` — 18 tests passing
- [x] 1.2c Replace inline element detection with tracker
- [x] 1.2d Run full test suite — 881 passed
- [x] 1.3a Extract `_stream_graph()` private method
- [x] 1.3b Extract `_update_position_title()` private method
- [x] 1.3c Refactor `send_message()` to orchestration-only (~67 lines incl docstring, down from 173)
- [x] 1.3d Run full test suite + TypeScript type check — 881 passed, tsc clean
- [x] 1.3e **Commit checkpoint: "Decompose send_message into single-responsibility units"**

---

## Phase 2: Unify Approval Control Flow (Backend + Frontend)

**Goal:** Make the backend authoritative for element status. Frontend sends structured intents; backend confirms status changes via `element_update`.

### 2.1 Add Structured Approval Protocol

**Files changed:** `src/api/websocket.py`, `frontend/src/types/api.ts`

**What:**
- Add a new WebSocket client message type: `"element_action"`
  ```typescript
  // Client sends:
  { type: "element_action", data: { element: "introduction", action: "approve" | "reject" | "regenerate", feedback?: string } }
  ```
- `websocket.py` translates this into a `send_message()` call with structured content that the graph can interpret unambiguously (not free-text "approve" that needs LLM classification)
- The agent receives structured input instead of having to classify free text

**Dependencies:**
- `websocket.py` — new message type handler (additive, no existing code changed)
- `frontend/src/types/api.ts` — new type (additive)
- `session_manager.py` — receives content string (no change needed yet)

**Anticipated effects:**
- New protocol runs alongside existing text-based flow (no breakage)
- Agent no longer needs to LLM-classify "approve" — it receives a structured intent

### 2.2 Remove Frontend Optimistic Status Updates

**Files changed:** `frontend/src/components/draft/ProductPanel.tsx`, `frontend/src/stores/draftStore.ts`, `frontend/src/hooks/useWebSocket.ts`

**What:**
- **ProductPanel.tsx:326-329**: Remove the optimistic `updateElement(sectionName, { locked: true, status: "approved" })` call. The approve button instead:
  1. Shows a pending/loading state on the button (spinner or disabled)
  2. Sends the `element_action` message
  3. Waits for backend `element_update` confirmation to update status
- **draftStore.ts**: `updateElement()` still exists for local-only state (notes, edited content), but status updates only come from backend
- **useWebSocket.ts**: `element_update` handler already updates draft store — this becomes the single source of truth for status

**Dependencies:**
- Phase 2.1 must be complete (structured protocol exists)
- `useWebSocket.ts` element_update handler (no change needed — already handles status updates)
- `ProductPanel.tsx` button rendering (conditional on status)

**Test plan:**
- Click approve → button shows pending → backend confirms → status updates to "approved"
- Click approve → backend rejects (e.g., QA failed) → status stays at previous state, user sees explanation
- Rapid double-click → second click disabled while first is pending
- Network disconnect during approve → pending state cleared on reconnect, status reflects backend truth
- `npx tsc --noEmit` passes, `npx vite build` succeeds

**Anticipated effects:**
- Eliminates state divergence between frontend and backend
- Approve flow becomes testable: mock backend response → verify UI state
- Slight perceived latency increase (~200-500ms) — mitigate with pending state UI

### 2.3 Backend: Structured Intent Bypass for Element Actions

**Files changed:** `src/api/session_manager.py` (or `websocket.py`), `src/nodes/routing.py`

**What:**
- When `websocket.py` receives an `element_action` message, it calls `send_message()` with metadata indicating this is a structured action (not free text):
  ```python
  await manager.send_message(
      session_id,
      content=f"[ACTION:approve] {element_name}",
      # OR: add a new parameter for structured actions
  )
  ```
- In `routing.py` or the intent classification node, structured actions bypass LLM classification entirely — they map directly to the correct handler node
- This is an **allowed exception** per CLAUDE.md: "Simple binary conditions (e.g., `should_end` → END)"

**Dependencies:**
- `session_manager.py` send_message signature (may need optional `action_type` parameter)
- `intent_classification_node.py` (may short-circuit for structured actions)
- `routing.py` (may add structured action route, allowed exception)

**Test plan:**
- Structured approve → element transitions to approved, no LLM call wasted
- Structured reject with feedback → element transitions to needs_revision, feedback preserved
- Free-text "I approve this" still works (LLM classification path preserved for chat input)
- Structured action on wrong phase → error returned, no state change

**Anticipated effects:**
- Eliminates the approve-as-text-for-LLM-classification antipattern
- Reduces LLM calls (no classification needed for button actions)
- Preserves free-text approval path for users who type in chat

### Phase 2 Punch List

- [x] 2.1a Add `element_action` message type + `ElementAction` type to `frontend/src/types/api.ts`
- [x] 2.1b Add `element_action` handler to `websocket.py` — translates to `[ACTION:<action>:<element>]` content prefix
- [x] 2.1c Wire ProductPanel approve/regenerate to send `element_action` messages
- [x] 2.1d `wsRef` exposed via `useWebSocket` → `sessionStore` for structured sends
- [x] 2.2a Remove optimistic status update from ProductPanel approve button
- [x] 2.2b Add `pendingAction` state + loading spinner on approve button
- [x] 2.2c `pendingAction` clears when `element.status` changes (backend confirmed via `element_update`)
- [x] 2.2d Approve button disabled while `pendingAction` or `isTyping` active
- [x] 2.3a Add `_ACTION_PREFIX_RE` regex in `intent_classification_node.py`
- [x] 2.3b Add `_classify_structured_action()` — maps approve→confirm, reject→reject, regenerate→modify_answer
- [x] 2.3c 18 unit tests for structured action protocol (regex, classification, intent mapping)
- [x] 2.3d Free-text "approve" still works (falls through to LLM classification)
- [x] 2.3e Full suite: 899 tests passing, tsc clean, vite build clean
- [x] 2.3f **Commit checkpoint: "Unify approval flow — backend authoritative for status"**

---

## Phase 3: Replace Suppression with Structured Agent Visibility

**Goal:** Replace regex-based message suppression with structured agent state that the UI can render meaningfully. The user always knows what the agent is doing.

### 3.1 Add Agent Activity State to WebSocket Protocol

**Files changed:** `src/api/session_manager.py`, `src/api/websocket.py`, `frontend/src/types/api.ts`

**What:**
- Add a new WebSocket server message type: `"activity_update"`
  ```typescript
  // Server sends:
  { type: "activity_update", data: {
      activity: "drafting" | "reviewing" | "waiting_for_approval" | "revising" | "evaluating",
      element?: string,        // Which element is being worked on
      detail?: string,         // Short human-readable detail
  }}
  ```
- Backend sends `activity_update` messages at node boundaries (extracted from the messages that are currently being generated and then suppressed)
- Node messages that describe internal activity (`"Let me draft..."`, `"Running QA review..."`) are replaced by structured activity updates at the source

**Dependencies:**
- `session_manager.py` — `_stream_graph()` (from Phase 1.3) sends activity updates
- `websocket.py` — new callback `on_activity` (additive)
- Frontend types — new `WSActivityUpdate` type

**Anticipated effects:**
- Agent state is communicated through structure, not natural language
- Frontend can render activity however it wants (progress bar, status line, icon)

### 3.2 Frontend Activity Indicator

**Files changed:** `frontend/src/stores/sessionStore.ts` (or new `activityStore.ts`), `frontend/src/components/draft/ProductPanel.tsx`

**What:**
- Store current agent activity in session or dedicated store
- ProductPanel shows per-element activity indicator (e.g., spinner + "Drafting..." next to element)
- Chat panel shows global activity indicator (e.g., "Agent is reviewing Introduction...")
- This replaces the current "show/system/suppress" classification for most messages

**Dependencies:**
- Phase 3.1 (activity_update messages exist)
- `useWebSocket.ts` — new handler for `activity_update`
- `ProductPanel.tsx` — element status rendering

**Test plan:**
- Agent drafts element → activity shows "Drafting Introduction..."
- Agent runs QA → activity shows "Reviewing Introduction..."
- Agent waits for approval → activity shows "Waiting for approval" with element name
- Activity clears on "done" message
- No activity shown during interview phase (not applicable)

### 3.3 Reduce Message Suppression to Minimal Set

**Files changed:** `frontend/src/hooks/useWebSocket.ts`

**What:**
- Now that structured activity updates replace internal pipeline messages at the source (Phase 3.1), dramatically reduce `classifyAgentMessage()`:
  - **Keep**: Content echo suppression (full draft text in chat — shown in panel instead)
  - **Keep**: Emoji-prefixed filler (if any remain)
  - **Remove**: All pattern-matching for "Let me draft...", "Running QA...", "Moving to next section...", etc. — these are now `activity_update` messages
  - **Remove**: "Do you approve this section?" suppression — this is now a structured `waiting_for_approval` activity, not a chat message
- Target: reduce `classifyAgentMessage()` from 138 lines to <30 lines

**Dependencies:**
- Phase 3.1 and 3.2 (activity system exists and renders)
- Nodes must be updated to send structured activities instead of chat messages (gradual — some nodes may still emit text)

**Test plan:**
- All agent states visible to user through activity indicators
- No "invisible loops" — if agent is stuck, user sees repeated activity
- Chat shows only user-relevant conversational messages
- Manual test: intentionally break a QA flow → verify user can see what's happening

**Anticipated effects:**
- User gains full visibility into agent state
- Debugging agent issues no longer requires backend logs
- classifyAgentMessage regex maintenance burden eliminated
- If nodes still emit some text messages, they pass through as "show" — safe fallback

### 3.4 Node Prompt Cleanup (Gradual)

**Files changed:** Various nodes in `src/nodes/`

**What:**
- Audit each node's `next_prompt` and message outputs
- Messages that describe internal state ("Let me draft X", "Moving to next section") should be replaced with activity signals or removed entirely
- Messages that are user-facing ("Here's the Introduction section for your review") stay as chat messages
- This is gradual — can be done node-by-node without breaking anything

**Dependencies:**
- Each node independently
- No cross-node dependencies for this change

### Phase 3 Punch List

- [x] 3.1a Define `activity_update` WebSocket message type in protocol docs
- [x] 3.1b Add `on_activity` callback to `send_message()` signature
- [x] 3.1c Emit activity updates in `_stream_graph()` at node boundaries
- [x] 3.1d Add `activity_update` handler to `websocket.py`
- [x] 3.2a Add `agentActivity` state + `setAgentActivity` to `sessionStore.ts`
- [x] 3.2b Add `activity_update` handler to `useWebSocket.ts` (+ clear on done/stopped)
- [x] 3.2c Render per-element activity in ProductPanel (spinner + label)
- [x] 3.2d Status dot now uses structured `activity` prop instead of `isAgentProcessing` heuristic
- [x] 3.3a Reduced `classifyAgentMessage()` from 138 lines to ~28 lines
- [x] 3.3b Kept only: content echo, FES detail, pipeline filler, interrupt prompt suppression
- [x] 3.3c TypeScript clean, 44 Phase 1-3 tests passing
- [ ] 3.4a Audit node messages — identify internal vs user-facing (gradual)
- [ ] 3.4b Replace internal messages with activity signals (node by node, gradual)
- [x] 3.4c **Commit checkpoint: "Replace message suppression with structured agent visibility"**

---

## Phase 4: Simplify Sequential Flow

**Goal:** Remove dead batch/parallel infrastructure while preserving the active parallel execution that provides real speedup.

**Audit finding:** The `asyncio.gather()` calls in `generate_element_node.py` and `qa_review_node.py` are ACTIVE and beneficial — they run literal-tier and LLM-tier sections in true parallel. The QA semaphore prevents rate-limiting. The prerequisite graph enforces correct generation order. Only the batch configuration functions and metadata were dead code.

### 4.1 Audit Parallel Infrastructure

**Files changed:** Analysis only (no code changes in this step)

**What:**
- Document exactly which parallel patterns exist:
  - Element snapshot + hash comparison (session_manager.py, now in `ElementChangeTracker`)
  - Pre-QA "drafted" status-only updates (partial content suppression)
  - Batch QA references in node code
  - Pre-population of element state from checkpoint
- For each pattern, determine: is this needed for sequential flow? What breaks if removed?

**Dependencies:** None (analysis only)

### 4.2 Simplify Element Streaming

**Files changed:** `src/api/element_tracker.py` (from Phase 1.2), `src/api/session_manager.py`

**What:**
- Since elements are processed sequentially, the `ElementChangeTracker` can be simplified:
  - Track only the `current_element_index` element (not all elements every event)
  - Remove pre-population from checkpoint (Phase 2 eliminated the need — frontend no longer makes optimistic status updates that need protecting from stale events)
  - Replace hash comparison with simple equality check on `(status, content)` tuple
- The "drafted" → status-only update logic remains (prevents "two drafts" flicker)

**Dependencies:**
- Phase 1.2 (tracker exists as separate unit)
- Phase 2 (optimistic updates removed, so checkpoint pre-population less critical)

**Test plan:**
- Single element generation → element_update sent once with final content
- Element with QA rewrite → status-only "drafted" update, then full "qa_passed" update
- No spurious element_updates for elements not being worked on
- Full drafting flow: all elements drafted, QA'd, approved

**Anticipated effects:**
- Simpler element tracking (fewer states to reason about)
- Marginal performance improvement (not iterating all elements every event)
- If parallel generation is added later, the tracker interface stays the same

### 4.3 Remove Dead Parallel Code Paths

**Files changed:** Various nodes, `src/api/session_manager.py`

**What:**
- Remove any code paths that exist solely for parallel generation support but are never executed in the sequential flow
- This requires careful analysis (Phase 4.1) — don't remove anything that serves the sequential flow
- Examples to look for:
  - Batch QA accumulation logic (if elements are always QA'd individually)
  - Parallel semaphore patterns (if generation is always sequential)
  - Pre-computation of "all elements ready for QA" checks

**Dependencies:**
- Phase 4.1 analysis complete
- Each removal is independent

**Test plan:**
- Full end-to-end drafting flow works
- Each removed code path has no test covering it (or tests are also removed)
- No regressions in existing test suite

### Phase 4 Punch List

- [x] 4.1a Audit all parallel patterns — `asyncio.gather` in generation & QA is ACTIVE and beneficial (real parallelism)
- [x] 4.1b Assessment: parallel generation/QA keeps, semaphore keeps, prerequisite graph keeps
- [x] 4.2 `ElementChangeTracker` already correct for parallel results (iterates all elements) — no simplification needed
- [x] 4.3a Removed dead batch functions: `get_drafting_batches()`, `get_sections_by_batch()`, `get_drafting_sequence()`
- [x] 4.3b Removed dead utility functions: `get_prompt_for_section()`, `get_sections_requiring_llm()`, `get_sections_by_prompt()`, `DEFAULT_SECTION_ORDER`
- [x] 4.3c Removed unused `"batch"` metadata key from all 18 SECTION_REGISTRY entries
- [x] 4.3d Updated `__all__` export list to match
- [x] 4.3e Full suite: 899 tests passing, tsc clean
- [x] 4.3f **Commit checkpoint: "Remove dead batch/parallel code from drafting config"**

---

## Phase 5: Documentation, Memory, and Policy Updates

**Goal:** Codify the architectural decisions made in Phases 1-4 into project documentation, CLAUDE.md policies, and auto-memory to prevent regression.

### 5.1 New ADRs

**Files created:**
- `docs/decisions/009-send-message-decomposition.md` — Documents the decomposition of `send_message()` and the principle that API methods should orchestrate, not implement business logic
- `docs/decisions/010-backend-authoritative-status.md` — Documents that element status is owned by the backend; frontend never sets status optimistically
- `docs/decisions/011-structured-agent-visibility.md` — Documents the replacement of message suppression with structured activity updates

### 5.2 Update CLAUDE.md Policies

**File changed:** `CLAUDE.md`

**Add new policy blocks:**

```markdown
## ⛔ NO GOD METHODS POLICY ⛔
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

```markdown
## ⛔ NO OPTIMISTIC STATUS POLICY ⛔
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

```markdown
## ⛔ NO MESSAGE SUPPRESSION FOR STATE POLICY ⛔
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

### 5.3 Update Module Documentation

**Files changed:**
- `docs/modules/api.md` — Document `transforms.py`, `element_tracker.py`, decomposed `send_message()`
- `docs/modules/frontend.md` — Document `element_action` protocol, removal of optimistic updates, activity indicators
- `docs/modules/nodes.md` — Update node message contract (structured activities vs chat messages)
- `docs/INDEX.md` — Add new ADRs, update module references

### 5.4 Update Auto-Memory

**File changed:** `/Users/davidhook/.claude/projects/-Users-davidhook-projects-agents-pd3r/memory/MEMORY.md`

**Add section:**
```markdown
## Architectural Policies (2026-03-10)
- send_message() must stay <50 lines; orchestration only, delegates to helpers
- QA transformation: single source of truth in src/api/transforms.py
- Element tracking: src/api/element_tracker.py (ElementChangeTracker class)
- Frontend NEVER sets element status optimistically — backend confirms via element_update
- Structured actions (approve/reject/regenerate) use element_action WS protocol, not free text
- Agent state visible via activity_update WS messages, not suppressed chat messages
- classifyAgentMessage should be <30 lines — most filtering moved to structured activities
- See docs/decisions/009, 010, 011 for rationale
```

### 5.5 Update MVP Roadmap

**File changed:** `docs/plans/mvp_roadmap.md`

**What:** Add "Phase 4.5: Architectural Remediation" section documenting this work and its completion status.

### Phase 5 Punch List

- [x] 5.1a Write ADR-009 (send_message decomposition)
- [x] 5.1b Write ADR-010 (backend-authoritative status)
- [x] 5.1c Write ADR-011 (structured agent visibility)
- [x] 5.2a Add NO GOD METHODS policy to CLAUDE.md
- [x] 5.2b Add NO OPTIMISTIC STATUS policy to CLAUDE.md
- [x] 5.2c Add NO MESSAGE SUPPRESSION FOR STATE policy to CLAUDE.md
- [x] 5.3a Update docs/modules/api.md (new files, protocol additions)
- [x] 5.3b Update docs/modules/frontend.md (activity, element_action, status lifecycle)
- [x] 5.3c Update docs/decisions/INDEX.md (ADRs 009-011)
- [x] 5.3d Update docs/INDEX.md (arch remediation → complete)
- [x] 5.4a Update auto-memory MEMORY.md (architectural policies section)
- [x] 5.5a Update mvp_roadmap.md (Phase 4.5 section)
- [x] 5.5b Update CLAUDE.md Current Focus section
- [x] 5.5c **Commit checkpoint: "Document architectural policies to prevent regression"**

---

## Dependency Map

```
Phase 1 (Backend decomposition)
  ├── 1.1 QA Transform ──────────────────────┐
  ├── 1.2 Element Tracker (depends on 1.1) ──┤
  └── 1.3 Orchestrator (depends on 1.1, 1.2) ┘
          │
Phase 2 (Approval unification) ← depends on Phase 1.3
  ├── 2.1 Structured Protocol (additive) ────┐
  ├── 2.2 Remove Optimistic (depends on 2.1) ┤
  └── 2.3 Backend Actions (depends on 2.1) ──┘
          │
Phase 3 (Agent visibility) ← depends on Phase 2
  ├── 3.1 Activity Protocol (additive) ──────┐
  ├── 3.2 Activity UI (depends on 3.1) ──────┤
  ├── 3.3 Reduce Suppression (depends on 3.2)┤
  └── 3.4 Node Cleanup (independent per node)┘
          │
Phase 4 (Simplification) ← depends on Phase 1.2, Phase 2.2
  ├── 4.1 Audit (analysis only) ─────────────┐
  ├── 4.2 Simplify Tracker (depends on 4.1) ─┤
  └── 4.3 Remove Dead Code (depends on 4.1) ─┘
          │
Phase 5 (Documentation) ← depends on Phases 1-4
  └── All items independent of each other
```

**Critical path:** 1.1 → 1.2 → 1.3 → 2.1 → 2.2/2.3 → 3.1 → 3.2 → 3.3

**Parallelizable:**
- Phase 4 can start after Phase 1.2 + 2.2 (doesn't need Phase 3)
- Phase 3.4 (node cleanup) can happen in parallel with Phase 4
- Phase 5 ADRs can be drafted during implementation (finalized at end)

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Phase 1 extraction introduces subtle streaming bug | Medium | High | Each extraction gets unit tests; integration test before/after each step |
| Phase 2 approval latency perceived as regression | Low | Medium | Pending state UI; measure actual latency before/after |
| Phase 3 activity messages too noisy | Low | Low | Activity updates are additive; can be hidden in UI without suppression |
| Phase 4 removes code that's actually needed | Medium | High | Phase 4.1 analysis step; remove one thing at a time with full test suite |
| Routing.py heuristic debt (619 lines) not addressed | N/A | Medium | **Intentionally deferred** — routing is a separate concern (ADR-006); this plan focuses on the 4 stated problems |

---

## What This Plan Does NOT Address

These are known issues that are out of scope for this remediation:

1. **Heuristic routing in `routing.py`** (619 lines of if/else) — Covered by existing ADR-006 and the migration plan in `docs/plans/langgraph_migration_plan.md`. This plan's Phase 2.3 adds a structured bypass for element actions, which is a step toward LLM-driven routing, but the full migration is separate work.

2. **Test infrastructure** (VCR cassettes) — Still incomplete per Phase 1 roadmap items. Not affected by this remediation.

3. **State compaction** — Already implemented at phase boundaries. Not affected.

---

## Execution Order Summary

```
Week 1: Phase 1 (decompose send_message)
  Day 1-2: Extract QA transform + tests
  Day 2-3: Extract element tracker + tests
  Day 3-4: Refactor send_message orchestration
  Day 4:   Integration test, commit

Week 2: Phase 2 (unify approval flow)
  Day 1:   Add element_action protocol (backend + frontend types)
  Day 2-3: Wire ProductPanel, remove optimistic updates
  Day 3-4: Add structured action bypass in backend
  Day 4:   Integration test, commit

Week 3: Phase 3 (agent visibility) + Phase 4 (simplification)
  Day 1:   Activity protocol + frontend store
  Day 2:   Activity UI rendering
  Day 3:   Reduce suppression, audit parallel patterns
  Day 4:   Simplify tracker, remove dead code, commit

Week 4: Phase 5 (documentation)
  Day 1-2: ADRs, CLAUDE.md policies, module docs
  Day 2:   Memory updates, roadmap updates, final commit
```
