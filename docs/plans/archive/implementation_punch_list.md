# PD3r MVP Implementation Punch List

> **Created**: 2026-01-14  
> **Based on**: [mvp_implementation_plan.md](mvp_implementation_plan.md)  
> **Status**: In Progress

---

## Legend

- `[ ]` Not started
- `[~]` In progress
- `[x]` Complete
- `[!]` Blocked / needs discussion

---

## Testing Philosophy

**Core Principle: No mocking LLM calls.**

- **Real LLM tests**: When testing prompts or LLM-dependent behavior, use actual LLM calls
- **Skip when stable**: Mark LLM tests with `@pytest.mark.llm` so they can be skipped when prompts are known to work
- **Unit tests focus on logic**: Test routing, state transformations, and validation without LLM
- **Integration tests use LLM**: Full flow tests should exercise real LLM calls
- **Environment gating**: LLM tests require `OPENAI_API_KEY`; skip gracefully when missing

```bash
# Run all tests (skips LLM if no API key)
pytest tests/

# Run only LLM tests (for prompt validation)
pytest tests/ -m llm

# Skip LLM tests explicitly
pytest tests/ -m "not llm"
```

---

## Completed Phases Summary

> ✅ **Phases 1-3 are complete.** Full task details moved to [Appendix A](#appendix-a-completed-phases).

| Phase | Status | Tests | Commit |
|-------|--------|-------|--------|
| **Phase 1: Foundation** | ✅ Complete | 28 tasks | "Phase 1: Foundation complete" |
| **Phase 2: Interview Flow** | ✅ Complete | 34 tasks | "Phase 2: Interview flow complete" |
| **Phase 3: FES & Drafting** | ✅ Complete | 62 tasks (287 tests) | "Phase 3: FES evaluation & drafting complete" |

**Key Deliverables from Phases 1-3**:
- `InterviewElement[T]` generic model with confirmation tracking
- Full intent classification with field extraction
- FES factor evaluation system (9 factors, grade-based level selection)
- Series-specific duty templates (GS-2210-13/14/15)
- Draft generation with QA review loop
- 287 passing tests

---

---

## Phase 4: Polish & Export (Week 4)

**Goal**: Complete UX and output

### ✅ 4.0 Interview→Drafting Transition Refactor (PREREQUISITE) - COMPLETE

**Problem**: The current graph has a design flaw in the interview completion flow:

1. **Overlapping responsibilities**: `check_interview_complete` and `prepare_next` both handle interview flow logic but are disconnected
2. **Missing user confirmation**: When `check_interview_complete` determines all fields are present, it routes **directly** to `evaluate_fes` → `gather_requirements` → `generate_element` without waiting for user confirmation
3. **MVP violation**: Per [mvp_implementation_plan.md](mvp_implementation_plan.md#52-sample-conversation-happy-path), the user should see the summary and confirm with "Does everything look ok?" before drafting begins

**Current Flow** (broken):
```
check_interview_complete → [complete] → evaluate_fes → gather_requirements → generate_element
                        → [incomplete] → user_input
```

**Correct Flow** (per MVP plan):
```
check_interview_complete → [complete] → user_input (show summary, ask "Does everything look ok?")
                        → [incomplete] → user_input (ask next question)
                        
classify_intent → [confirm, phase=requirements] → evaluate_fes
              → [reject/modify, phase=requirements] → map_answers
```

**Design Decision**: Consolidate into `prepare_next` with interview-complete handling:
- `prepare_next` already handles: missing fields, fields needing confirmation
- Add: interview-complete summary with confirmation prompt
- `check_interview_complete` becomes a **pure check** that sets `phase: "requirements"` when complete
- **User must confirm** before FES evaluation begins
- Routing handles `confirm` intent in `requirements` phase → `evaluate_fes`

| ID | Task | File | Status | Notes |
|----|------|------|--------|-------|
| 4.0.1 | Refactor `check_interview_complete_node` to pure check | `src/nodes/check_interview_complete_node.py` | [x] | Only sets phase="requirements" if complete, no routing decision |
| 4.0.2 | Move summary display to `prepare_next_node` | `src/nodes/prepare_next_node.py` | [x] | Show summary + "Does everything look ok?" when interview complete |
| 4.0.3 | Update routing: `confirm` + `requirements` phase → `evaluate_fes` | `src/nodes/routing.py` | [x] | `_route_requirements_phase()` handles transition |
| 4.0.4 | Update graph: `check_interview_complete` → `prepare_next` always | `src/graphs/main_graph.py` | [x] | Remove direct edge to `evaluate_fes` |
| 4.0.5 | Add conditional edge: `classify_intent` → `evaluate_fes` | `src/graphs/main_graph.py` | [x] | When phase=requirements and intent=confirm |
| 4.0.6 | Update tests for new interview→drafting transition | `tests/test_node_check_complete.py`, `tests/test_unit_routing.py` | [x] | Verify user confirmation required |
| 4.0.7 | Verify graph compiles and exports correctly | `output/graphs/main_graph.mmd` | [x] | Visual confirmation |
| 4.0.8 | Run full test suite | — | [x] | `pytest tests/` all green (329 passed) |

---

### ✅ 4.1 Final Document Assembly & Review Phase - COMPLETE

**Goal**: Assemble all draft elements into a final document and implement the `review` phase.

**Current Gap**: The MVP plan describes a distinct `review` phase where Pete presents the **complete PD** for final review before export. Currently the graph goes directly from `drafting` → `end_conversation`.

| ID | Task | File | Status | Notes |
|----|------|------|--------|---------|
| 4.1.1 | Implement `assemble_final_document()` | `src/utils/document.py` | [x] | Combine all draft elements |
| 4.1.2 | Add supervisory elements if applicable | `src/utils/document.py` | [x] | Conditional inclusion via `should_include_supervisory_elements()` |
| 4.1.3 | Create final review summary | `src/utils/document.py` | [x] | `create_review_summary()` with status icons |
| 4.1.4 | Implement `finalize_node` | `src/nodes/finalize_node.py` | [x] | Final approval flow + `handle_element_revision_request()` |
| 4.1.5 | Set `phase: "review"` when all elements approved | `src/nodes/routing.py` | [x] | `route_after_advance_element()` → finalize |
| 4.1.6 | Show assembled document in review phase | `src/nodes/prepare_next_node.py` | [x] | `_prepare_review_phase_prompt()` |
| 4.1.7 | Allow late revisions to ANY element during review | `src/nodes/finalize_node.py` | [x] | `handle_element_revision_request()` with keyword matching |
| 4.1.8 | Add element selection to `modify_answer` intent | `src/models/intent.py` | [x] | `ElementModification` model + `element_modifications` field |
| 4.1.9 | Update routing for review phase element revision | `src/nodes/routing.py` | [x] | `_route_review_phase()` → `handle_element_revision` |

### ✅ 4.2 Export Functionality - COMPLETE

| ID | Task | File | Status | Notes |
|----|------|------|--------|-------|
| 4.2.1 | Implement markdown export | `src/tools/export_tools.py` | [x] | `export_to_markdown()` |
| 4.2.2 | Implement Word export (python-docx) | `src/tools/export_tools.py` | [x] | `export_to_word()` |
| 4.2.3 | Add export path configuration | `src/tools/export_tools.py` | [x] | Default to `output/` |
| 4.2.4 | Generate filename from position title | `src/tools/export_tools.py` | [x] | `sanitize_filename()`, `generate_filename()` |
| 4.2.5 | Write unit tests for export functions | `tests/test_unit_export.py` | [x] | 30 tests |
| 4.2.6 | Add `request_export` intent to `IntentClassification` | `src/models/intent.py` | [x] | With `ExportRequest` model (word/markdown/none) |
| 4.2.7 | Update intent classification prompt for export detection | `src/prompts/templates/intent_classification.jinja` | [x] | Complete phase export handling |
| 4.2.8 | Add export handling to complete phase routing | `src/nodes/routing.py` | [x] | `request_export` → `export_document` |
| 4.2.9 | Create `export_document_node` | `src/nodes/export_node.py` | [x] | Call export tools based on format |
| 4.2.10 | Add `export_document` to graph | `src/graphs/main_graph.py` | [x] | With `route_after_export` |
| 4.2.11 | Write unit tests for export node | `tests/test_node_export.py` | [x] | 15 tests |

**467 total tests passing** (+71 new tests from 4.2 + 4.4 combined)

### 4.3 Conversation Flow Polish

#### ✅ 4.3.A "Write Another?" Flow - COMPLETE

**Goal**: Allow users to start another PD without creating a new session.

**Implementation**:
- Added `wants_another: Optional[bool]` and `is_restart: bool` to `AgentState`
- `end_conversation_node` asks "Would you like to write another PD?" when `wants_another=None`
- `handle_write_another_node` processes user response and sets `wants_another` flag
- `route_after_end_conversation` routes: `user_input` (ask) → `init` (restart) → `__end__` (done)
- `init_node` detects `is_restart=True` and shows restart greeting while resetting state

| ID | Task | File | Status | Notes |
|----|------|------|--------|-------|
| 4.3.A.1 | Add `wants_another: Optional[bool]` to `AgentState` | `src/models/state.py` | [x] | None = not asked, True/False after response |
| 4.3.A.2 | Add `is_restart: bool` to `AgentState` | `src/models/state.py` | [x] | Signals init_node to reset interview data |
| 4.3.A.3 | Update `end_conversation_node` with write another prompt | `src/nodes/end_conversation_node.py` | [x] | Ask "Would you like to write another PD?" |
| 4.3.A.4 | Create `route_after_end_conversation()` function | `src/nodes/routing.py` | [x] | Check `wants_another` state flag |
| 4.3.A.5 | Update `init_node` to handle restart | `src/nodes/init_node.py` | [x] | Reset interview_data, draft_elements, keep session |
| 4.3.A.6 | Add conditional edge from `end_conversation` | `src/graphs/main_graph.py` | [x] | → `user_input` / `init` / `END` |
| 4.3.A.7 | Write unit tests for restart flow | `tests/test_unit_routing.py` | [x] | Route decisions based on wants_another |
| 4.3.A.8 | Write integration test for "write another" | `tests/test_e2e.py` | [x] | Full restart cycle |

**469 total tests passing** (+22 new tests from 4.3.A)

#### ✅ 4.3.B Personality Polish - COMPLETE

**Implementation**:
- Created `src/utils/personality.py` with phrase rotation utilities
- Phrase categories: acknowledgment, transition, working, completion, confirmation, revision, back-to-topic
- Rotation algorithm avoids immediate repeats (last 2 phrases skipped)
- Integrated phrases into: `map_answers_node`, `handle_revision_node`, `generate_element_node`
- 29 unit tests for phrase rotation and convenience functions

| ID | Task | File | Status | Notes |
|----|------|------|--------|-------|
| 4.3.B.1 | Implement "Write another?" flow | `src/nodes/end_conversation_node.py` | [x] | (Completed in 4.3.A) |
| 4.3.B.2 | Add acknowledgment phrase rotation | `src/utils/personality.py` | [x] | 7 phrases, integrated into map_answers_node |
| 4.3.B.3 | Add transition phrase rotation | `src/utils/personality.py` | [x] | 7 phrases, used via transition_to() |
| 4.3.B.4 | Add working phrase rotation | `src/utils/personality.py` | [x] | 7 phrases, used via get_working() |
| 4.3.B.5 | Fine-tune Pete's personality | `src/prompts/templates/` | [x] | Integrated via node updates per Appendix C |

**498 total tests passing** (+29 new personality tests)

#### ✅ 4.3.C Drafting Preamble - COMPLETE

**Implementation**:
- Updated `gather_draft_requirements_node` to show a friendly preamble explaining PD structure
- Lists all elements that will be drafted (filtered by supervisory status)
- Shows element count ("N sections total")
- Notes supervisory factors when applicable
- 6 new tests for preamble content

| ID | Task | File | Status | Notes |
|----|------|------|--------|-------|
| 4.3.C.1 | Add drafting preamble message | `src/nodes/gather_draft_requirements_node.py` | [x] | "We're ready to write! A PD consists of..." |
| 4.3.C.2 | List elements that will be generated | `src/nodes/gather_draft_requirements_node.py` | [x] | Based on DRAFT_ELEMENT_NAMES + supervisory |
| 4.3.C.3 | Include estimated element count | `src/nodes/gather_draft_requirements_node.py` | [x] | "That's N sections total" |

**504 total tests passing** (+6 new preamble tests)

#### ✅ 4.3.D Enhanced Rewrite Context & Model Escalation - COMPLETE

**Goal**: When a rewrite is triggered (QA failure OR user revision request), provide richer context and escalate model capabilities to produce stronger rewrites.

**Implementation**:
- Added `DraftAttempt` model to track draft history with QA results and user feedback
- Added `draft_history`, `rewrite_reason`, `is_rewrite`, `attempt_number` to `DraftElement`
- Added `save_to_history()` method called by `qa_review_node` and `handle_revision_node`
- Added `get_rewrite_context()` method to build context for rewrite template
- Created `draft_rewrite.jinja` template with rich context showing previous attempts and failures
- Added model escalation utilities: `get_rewrite_model()`, `get_model_for_attempt()`, `MODEL_ESCALATION_MAP`
- Rewrites use lower temperature (0.1) for more focused output
- Updated `generate_element_node` to detect rewrites and use escalated model/template
- 22 new tests for rewrite context, history, and model escalation

| ID | Task | File | Status | Notes |
|----|------|------|--------|-------|
| 4.3.D.1 | Add `draft_history` field to `DraftElement` | `src/models/draft.py` | [x] | List[DraftAttempt] |
| 4.3.D.2 | Store previous draft in history on rewrite | `src/models/draft.py` | [x] | `save_to_history()` method |
| 4.3.D.3 | Add `rewrite_reason` field to `DraftElement` | `src/models/draft.py` | [x] | Literal["qa_failure", "user_revision", None] |
| 4.3.D.4 | Capture specific failure reasons from QA | `src/nodes/qa_review_node.py` | [x] | In `save_to_history()` |
| 4.3.D.5 | Create `draft_rewrite.jinja` template | `src/prompts/templates/draft_rewrite.jinja` | [x] | Full context template |
| 4.3.D.6 | Create `get_rewrite_model()` utility | `src/utils/__init__.py` | [x] | Returns escalated ChatOpenAI |
| 4.3.D.7 | Implement model escalation logic | `src/utils/__init__.py` | [x] | MODEL_ESCALATION_MAP |
| 4.3.D.8 | Add temperature reduction for rewrites | `src/utils/__init__.py` | [x] | REWRITE_TEMPERATURE = 0.1 |
| 4.3.D.9 | Update `generate_element_node` to detect rewrite | `src/nodes/generate_element_node.py` | [x] | Check `element.is_rewrite` |
| 4.3.D.10 | Use rewrite template + escalated model on rewrite | `src/nodes/generate_element_node.py` | [x] | Conditional selection |
| 4.3.D.11 | Include user feedback in rewrite context | `src/models/draft.py` | [x] | In `get_rewrite_context()` |
| 4.3.D.12 | Write unit tests for rewrite context building | `tests/test_unit_draft.py` | [x] | 19 tests for DraftAttempt/RewriteContext |
| 4.3.D.13 | Write integration test for rewrite improvement | `tests/test_integration_foundation.py` | [x] | 3 tests for template/model escalation |

**526 total tests passing** (+22 new rewrite context tests)

### 4.4 RAG Integration & Knowledge Base - COMPLETE

**Goal**: Enable Pete to answer HR-specific questions using OPM guidance documents.

**Knowledge Sources** (in `knowledge/unprocessed_pdfs/`):
- OPM position classification standards
- Federal Evaluation System (FES) guidance
- Series-specific classification guides (e.g., 2210 IT Management)
- Supervisory position evaluation guides

#### 4.4.A PDF Processing & Vector Store Setup

| ID | Task | File | Status | Notes |
|----|------|------|--------|-------|
| 4.4.A.1 | Add `langchain-community`, `pypdf`, vector store deps | `pyproject.toml` | [x] | `chromadb`, `langchain-chroma`, `pypdf` |
| 4.4.A.2 | Create PDF loader utility | `src/tools/pdf_loader.py` | [x] | `load_pdf()`, `load_all_pdfs()` |
| 4.4.A.3 | Implement text chunking strategy | `src/tools/pdf_loader.py` | [x] | `chunk_documents()`, 1000 char chunks, 100 overlap |
| 4.4.A.4 | Create embedding function wrapper | `src/tools/embeddings.py` | [x] | `get_embeddings()` with `text-embedding-3-small` |
| 4.4.A.5 | Build vector store from chunks | `src/tools/vector_store.py` | [x] | `build_vector_store()`, persists to `knowledge/vector_store/` |
| 4.4.A.6 | Create one-time ingestion script | `scripts/ingest_knowledge.py` | [x] | `poetry run python scripts/ingest_knowledge.py` |
| 4.4.A.7 | Add `.gitignore` entry for vector store | `.gitignore` | [x] | Excludes `knowledge/vector_store/` |
| 4.4.A.8 | Document ingestion process | `knowledge/README.md` | [x] | Full document inventory + download URLs |

#### 4.4.B RAG Query Integration

| ID | Task | File | Status | Notes |
|----|------|------|--------|-------|
| 4.4.B.1 | Create `rag_lookup()` function | `src/tools/rag_tools.py` | [x] | `rag_lookup()` + `format_rag_context()` |
| 4.4.B.2 | Create RAG prompt template | `src/prompts/templates/rag_answer.jinja` | [x] | Includes context injection + source citations |
| 4.4.B.3 | Add `is_hr_question` flag to intent classification | `src/models/intent.py` | [x] | `is_hr_specific` field on `QuestionInfo` |
| 4.4.B.4 | Update intent classification prompt for HR detection | `src/prompts/templates/intent_classification.jinja` | [x] | Examples of OPM/FES/classification questions |
| 4.4.B.5 | Update `answer_question_node` for RAG routing | `src/nodes/answer_question_node.py` | [x] | `answer_question_with_rag()` when `is_hr_specific` |
| 4.4.B.6 | Add source citation to RAG answers | `src/nodes/answer_question_node.py` | [x] | `get_source_citations()` in `rag_tools.py` |
| 4.4.B.7 | Write unit tests for RAG retrieval | `tests/test_unit_rag.py` | [x] | 14 tests with mocked vector store |
| 4.4.B.8 | Write integration test for HR question flow | `tests/test_integration_rag.py` | [x] | 6 LLM-marked tests with real embeddings |

### 4.5 Error Handling & Recovery

| ID | Task | File | Status | Notes |
|----|------|------|--------|-------|
| 4.5.1 | Create custom exceptions module | `src/exceptions.py` | [x] | PD3rException hierarchy |
| 4.5.2 | Add LLM error handling with retry | `src/utils/llm.py` | [x] | Exponential backoff, tracing support |
| 4.5.3 | Add graceful recovery messages | `src/utils/recovery.py` | [x] | Recovery utilities + user messages |
| 4.5.4 | Handle checkpointer errors | `src/graphs/main_graph.py` | [x] | SafeCheckpointer wrapper |
| 4.5.5 | Write error handling tests | `tests/test_error_handling.py` | [x] | 29 tests |
| 4.5.6 | Add `validation_error` field to `AgentState` | `src/models/state.py` | [x] | Track validation failures |
| 4.5.7 | Update `map_answers_node` to set validation errors | `src/nodes/map_answers_node.py` | [x] | Series/grade validation |
| 4.5.8 | Display validation error in `prepare_next` prompt | `src/nodes/prepare_next_node.py` | [x] | Re-prompt with error message |
| 4.5.9 | Write test for invalid series/grade re-prompt | `tests/test_error_handling.py` | [x] | TestValidationErrorInMapAnswers |

**555 total tests passing** (+29 new error handling tests)

### 4.6 CLI & Entry Point

| ID | Task | File | Status | Notes |
|----|------|------|--------|-------|
| 4.6.1 | Update `main.py` with full conversation loop | `src/main.py` | [x] | Invoke graph, handle Command(resume=) |
| 4.6.2 | Add `--trace` flag support | `src/main.py` | [x] | LOCAL_TRACING environment |
| 4.6.3 | Add session ID management | `src/main.py` | [x] | For checkpointer |
| 4.6.4 | Add graceful exit handling (Ctrl+C) | `src/main.py` | [x] | Save state on exit |
| 4.6.5 | Persist session ID to file | `src/main.py` | [x] | `output/.sessions/` |
| 4.6.6 | Detect existing session on startup | `src/main.py` | [x] | Offer to resume or start fresh |
| 4.6.7 | Add `is_resume` flag to `AgentState` | `src/models/state.py` | [x] | Signals init_node to show resume greeting |
| 4.6.8 | Add resume greeting in `init_node` | `src/nodes/init_node.py` | [x] | "Welcome back! You were working on [title]" |

**560 total tests passing** (+5 new init_node tests for resume flow) |


### 4.7 End-to-End Testing

#### 4.7.A Test Infrastructure

| ID | Task | File | Status | Notes |
|----|------|------|--------|-------|
| 4.7.A.1 | Create minimal test interview config | `src/config/test_config.py` | [x] | 4 fields: title, series, grade, duties |
| 4.7.A.2 | Build ScriptedInputProvider class | `scripts/run_e2e_test.py` | [x] | Automated test answers |
| 4.7.A.3 | Create e2e test runner script | `scripts/run_e2e_test.py` | [x] | `poetry run python scripts/run_e2e_test.py` |
| 4.7.A.4 | Add phase transition handling | `src/nodes/prepare_next_node.py` | [x] | init → interview transition |
| 4.7.A.5 | Add fallback field extraction | `src/nodes/map_answers_node.py` | [x] | Direct extraction without LLM |
| 4.7.A.6 | Fix InterviewData model fields | `src/models/interview.py` | [x] | Added missing fields |

#### 4.7.B Test Scenarios

| ID | Task | File | Status | Notes |
|----|------|------|--------|-------|
| 4.7.B.1 | Happy path: full conversation to export | `tests/test_e2e.py` | [ ] | Interview → draft → export (needs LLM) |
| 4.7.B.2 | Test: Field modification mid-interview | `tests/test_e2e.py` | [ ] | "Change X to Y" |
| 4.7.B.3 | Test: Question handling without derailing | `tests/test_e2e.py` | [ ] | |
| 4.7.B.4 | Test: Revision requests in drafting | `tests/test_e2e.py` | [ ] | |
| 4.7.B.5 | Test: "Write another?" restart | `tests/test_e2e.py` | [ ] | |
| 4.7.B.6 | Test: Session resume from checkpoint | `tests/test_e2e.py` | [ ] | |

**Current e2e test status:** 10 non-LLM tests pass, 3 LLM tests skip without API key. Flow verified through init → interview → requirements → drafting phases.

### 4.8 Documentation

| ID | Task | File | Status | Notes |
|----|------|------|--------|-------|
| 4.8.1 | Update README with usage instructions | `README.md` | [ ] | |
| 4.8.2 | Document all node behaviors | `docs/modules/nodes.md` | [ ] | |
| 4.8.3 | Document prompt templates | `docs/modules/prompts.md` | [ ] | |
| 4.8.4 | Document state model | `docs/modules/models.md` | [ ] | |
| 4.8.5 | Create user guide | `docs/user_guide.md` | [ ] | How to use Pete |

### Phase 4 Checklist
- [x] All 4.0.x tasks complete (Interview→Drafting refactor - PREREQUISITE)
- [x] All 4.1.x tasks complete (Final document assembly & review phase)
- [x] All 4.2.x tasks complete (Export functionality & intent)
- [x] All 4.3.A.x tasks complete (Write another flow)
- [x] All 4.3.B.x tasks complete (Personality polish)
- [x] All 4.3.C.x tasks complete (Drafting preamble)
- [x] All 4.3.D.x tasks complete (Enhanced rewrite context & model escalation)
- [x] All 4.4.A.x tasks complete (PDF processing & vector store)
- [x] All 4.4.B.x tasks complete (RAG query integration)
- [x] All 4.5.x tasks complete (Error handling & recovery) ✅
- [x] All 4.6.x tasks complete (CLI & entry point) ✅
- [x] All 4.7.A.x tasks complete (Test infrastructure) ✅
- [ ] All 4.7.B.x tasks complete (Test scenarios - needs LLM)
- [ ] All 4.8.x tasks complete
- [x] `pytest tests/` passes (560 tests)
- [x] E2E test infrastructure works (10 tests pass, 3 LLM skip)
- [ ] Commit: "Phase 4: MVP complete"

---

## Summary

| Phase | Tasks | Est. Effort |
|-------|-------|-------------|
| Phase 1: Foundation | 28 tasks | Week 1 |
| Phase 2: Interview Flow | 34 tasks | Week 2 |
| Phase 3: FES Evaluation & Draft | 62 tasks | Week 3 |
| Phase 4: Polish & Export | ~85 tasks | Week 4+ |
| **Total** | **~209 tasks** | **5 weeks** |

**Phase 4 Breakdown**:
- 4.0: Interview→Drafting refactor (8 tasks) - PREREQUISITE
- 4.1: Final document & review phase (9 tasks)
- 4.2: Export functionality (9 tasks)
- 4.3.A: Write another flow (8 tasks)
- 4.3.B: Personality polish (5 tasks)
- 4.3.C: Drafting preamble (3 tasks)
- 4.3.D: Enhanced rewrite context (13 tasks)
- 4.4.A: PDF processing & vector store (8 tasks)
- 4.4.B: RAG query integration (8 tasks)
- 4.5: Error handling (9 tasks)
- 4.6: CLI & entry point (8 tasks)
- 4.7: End-to-end testing (6 tasks)
- 4.8: Documentation (5 tasks)

---

## Quick Reference: File Creation Order

```
# Phase 1
src/models/interview.py          # InterviewElement, InterviewData
src/models/intent.py             # IntentClassification, FieldMapping
src/constants.py                 # REQUIRED_FIELDS, FIELD_PROMPTS
src/nodes/init_node.py
src/nodes/user_input_node.py
src/nodes/intent_classification_node.py
src/nodes/routing.py
src/nodes/end_conversation_node.py

# Phase 2
src/prompts/templates/intent_classification.jinja
src/prompts/templates/answer_question.jinja
src/nodes/map_answers_node.py
src/nodes/answer_question_node.py
src/nodes/prepare_next_node.py
src/nodes/check_interview_complete_node.py
src/utils/formatting.py
src/validation.py (optional)

# Phase 3 - FES & Drafting
src/models/fes.py                # FESFactorLevel, FESEvaluation, GradeCutoff
src/models/duties.py             # DutySection, SeriesDutyTemplate
src/models/requirements.py       # DraftRequirement, DraftRequirements
src/models/draft.py              # DraftElement, QACheckResult, QAReview
src/config/fes_factors.py        # FES_FACTOR_LEVELS, GRADE_CUTOFFS
src/config/series_templates.py   # SERIES_DUTY_TEMPLATES
src/nodes/evaluate_fes_factors_node.py
src/nodes/gather_draft_requirements_node.py
src/nodes/generate_element_node.py
src/nodes/qa_review_node.py
src/nodes/handle_revision_node.py
src/prompts/templates/draft_introduction.jinja
src/prompts/templates/draft_major_duties.jinja
src/prompts/templates/draft_factor_*.jinja (5 templates for factors 1-5)
src/prompts/templates/draft_other_significant_factors.jinja
src/prompts/templates/qa_review.jinja

# Phase 4
src/utils/document.py
src/utils/personality.py
src/tools/export_tools.py
src/tools/rag_tools.py
src/exceptions.py
src/utils/llm.py
src/nodes/finalize_node.py
```

---

## Notes

- Mark tasks `[x]` when complete

---

## Appendix A: Completed Phases (Archive)

*Moved from main body on completion. See "Completed Phases Summary" section for overview.*

### Phase 1: Foundation (Week 1) ✅

**Goal**: Core models, basic graph, interrupt pattern

#### 1.1 Core Models

| ID | Task | File | Status |
|----|------|------|--------|
| 1.1.1 | Create `InterviewElement[T]` generic model | `src/models/interview.py` | [x] |
| 1.1.2 | Implement `InterviewElement.is_set` property | `src/models/interview.py` | [x] |
| 1.1.3 | Implement `InterviewElement.set_value()` method | `src/models/interview.py` | [x] |
| 1.1.4 | Implement `InterviewElement.confirm()` method | `src/models/interview.py` | [x] |
| 1.1.5 | Create `InterviewData` model using `InterviewElement` fields | `src/models/interview.py` | [x] |
| 1.1.6 | Implement `InterviewData.get_fields_needing_confirmation()` | `src/models/interview.py` | [x] |
| 1.1.7 | Update `AgentState` TypedDict with new fields | `src/models/state.py` | [x] |
| 1.1.8 | Create `IntentClassification` Pydantic model | `src/models/intent.py` | [x] |
| 1.1.9 | Create `FieldMapping` Pydantic model | `src/models/intent.py` | [x] |
| 1.1.10 | Write unit tests for `InterviewElement` | `tests/test_unit_interview.py` | [x] |
| 1.1.11 | Write unit tests for `InterviewData` | `tests/test_unit_interview.py` | [x] |

#### 1.2 Constants & Configuration

| ID | Task | File | Status |
|----|------|------|--------|
| 1.2.1 | Create `REQUIRED_FIELDS` list | `src/constants.py` | [x] |
| 1.2.2 | Create `CONDITIONAL_FIELDS` dict | `src/constants.py` | [x] |
| 1.2.3 | Create `FIELD_PROMPTS` dict | `src/constants.py` | [x] |
| 1.2.4 | Create `FIELD_CONFIG` dict | `src/constants.py` | [x] |
| 1.2.5 | Create `fields.json` configuration file | `src/config/fields.json` | [x] |
| 1.2.6 | Load constants from JSON config | `src/constants.py` | [x] |

#### 1.3 Core Nodes

| ID | Task | File | Status |
|----|------|------|--------|
| 1.3.1 | Implement `init_node` | `src/nodes/init_node.py` | [x] |
| 1.3.2 | Implement `user_input_node` with `interrupt()` | `src/nodes/user_input_node.py` | [x] |
| 1.3.3 | Create basic intent classification | `src/nodes/intent_classification_node.py` | [x] |
| 1.3.4 | Implement basic `route_by_intent` function | `src/nodes/routing.py` | [x] |
| 1.3.5 | Write unit tests for `init_node` | `tests/test_node_init.py` | [x] |
| 1.3.6 | Write unit tests for routing logic | `tests/test_unit_routing.py` | [x] |

#### 1.4 Graph Assembly

| ID | Task | File | Status |
|----|------|------|--------|
| 1.4.1 | Update `main_graph.py` with new `AgentState` | `src/graphs/main_graph.py` | [x] |
| 1.4.2 | Add `init` node to graph | `src/graphs/main_graph.py` | [x] |
| 1.4.3 | Add `user_input` node to graph | `src/graphs/main_graph.py` | [x] |
| 1.4.4 | Add `classify_intent` node to graph | `src/graphs/main_graph.py` | [x] |
| 1.4.5 | Add conditional edges for routing | `src/graphs/main_graph.py` | [x] |
| 1.4.6 | Configure `MemorySaver` checkpointer | `src/graphs/main_graph.py` | [x] |
| 1.4.7 | Add `end_conversation_node` | `src/nodes/end_conversation_node.py` | [x] |
| 1.4.8 | Export graph visualization | `output/graphs/` | [x] |

#### 1.5 Integration Testing

| ID | Task | File | Status |
|----|------|------|--------|
| 1.5.1 | Test: Can greet user | `tests/test_integration_foundation.py` | [x] |
| 1.5.2 | Test: Can handle "yes" confirmation | `tests/test_integration_foundation.py` | [x] |
| 1.5.3 | Test: Can handle "no" rejection | `tests/test_integration_foundation.py` | [x] |
| 1.5.4 | Test: Checkpointer saves state | `tests/test_integration_foundation.py` | [x] |

---

### Phase 2: Interview Flow (Week 2) ✅

**Goal**: Complete interview collection with confirmation handling

#### 2.1 Intent Classification (Full)

| ID | Task | File | Status |
|----|------|------|--------|
| 2.1.1 | Create `intent_classification.jinja` template | `src/prompts/templates/` | [x] |
| 2.1.2 | Full `IntentClassification` schema with all intents | `src/models/intent.py` | [x] |
| 2.1.3 | Implement LLM-powered `intent_classification_node` | `src/nodes/intent_classification_node.py` | [x] |
| 2.1.4 | Add `FieldMapping` extraction to intent classification | `src/nodes/intent_classification_node.py` | [x] |
| 2.1.5 | Write tests for intent parsing | `tests/test_unit_intent.py` | [x] |

#### 2.2 Answer Mapping

| ID | Task | File | Status |
|----|------|------|--------|
| 2.2.1 | Implement `map_answers_node` | `src/nodes/map_answers_node.py` | [x] |
| 2.2.2 | Handle uncertain extractions | `src/nodes/map_answers_node.py` | [x] |
| 2.2.3 | Build mapped summary response | `src/nodes/map_answers_node.py` | [x] |
| 2.2.4 | Update `missing_fields` list | `src/nodes/map_answers_node.py` | [x] |
| 2.2.5 | Write unit tests for `map_answers_node` | `tests/test_node_map_answers.py` | [x] |

#### 2.3 Confirmation Flow

| ID | Task | File | Status |
|----|------|------|--------|
| 2.3.1 | Implement confirmation prompt generation | `src/nodes/prepare_next_node.py` | [x] |
| 2.3.2 | Handle user confirmation response | `src/nodes/map_answers_node.py` | [x] |
| 2.3.3 | Handle user correction response | `src/nodes/map_answers_node.py` | [x] |
| 2.3.4 | Update routing for confirmation states | `src/nodes/routing.py` | [x] |
| 2.3.5 | Write integration test for confirmation flow | `tests/` | [~] |

#### 2.4 Question Handling

| ID | Task | File | Status |
|----|------|------|--------|
| 2.4.1 | Create `answer_question.jinja` template | `src/prompts/templates/` | [x] |
| 2.4.2 | Implement `answer_question_node` | `src/nodes/answer_question_node.py` | [x] |
| 2.4.3 | Store pending field, answer, return to flow | `src/nodes/answer_question_node.py` | [x] |
| 2.4.4 | Write tests for question handling | `tests/test_node_answer_question.py` | [x] |

#### 2.5 Field Validation

| ID | Task | File | Status |
|----|------|------|--------|
| 2.5.1 | Implement series validation (4-digit) | `src/validation.py` | [x] |
| 2.5.2 | Implement grade validation (GS-XX) | `src/validation.py` | [x] |
| 2.5.3 | Implement organization parsing | `src/validation.py` | [x] |
| 2.5.4 | Add validation error messages | `src/validation.py` | [x] |
| 2.5.5 | Write validation unit tests | `tests/test_unit_validation.py` | [x] |

#### 2.6 Interview Summary & Completion

| ID | Task | File | Status |
|----|------|------|--------|
| 2.6.1 | Implement `format_interview_summary()` | `src/nodes/check_interview_complete_node.py` | [x] |
| 2.6.2 | Implement `check_interview_complete_node` | `src/nodes/check_interview_complete_node.py` | [x] |
| 2.6.3 | Handle late field modifications | `src/nodes/map_answers_node.py` | [x] |
| 2.6.4 | Add conditional field triggering | `src/nodes/map_answers_node.py` | [x] |
| 2.6.5 | Write integration test for full interview | `tests/` | [~] |

#### 2.7 Graph Updates

| ID | Task | File | Status |
|----|------|------|--------|
| 2.7.1 | Add `map_answers` node to graph | `src/graphs/main_graph.py` | [x] |
| 2.7.2 | Add `answer_question` node to graph | `src/graphs/main_graph.py` | [x] |
| 2.7.3 | Add `check_interview_complete` node to graph | `src/graphs/main_graph.py` | [x] |
| 2.7.4 | Add `prepare_next` node to graph | `src/graphs/main_graph.py` | [x] |
| 2.7.5 | Update conditional edges for interview flow | `src/graphs/main_graph.py` | [x] |
| 2.7.6 | Export updated graph visualization | `output/graphs/` | [x] |

---

### Phase 3: Requirements & Draft Generation (Week 3) ✅

**Goal**: FES factor evaluation, series-specific duties, and requirement-driven drafting

#### 3.1 FES Business Rules Models

| ID | Task | File | Status |
|----|------|------|--------|
| 3.1.1 | Create `FESFactorLevel` model | `src/models/fes.py` | [x] |
| 3.1.2 | Create `FESEvaluation` model | `src/models/fes.py` | [x] |
| 3.1.3 | Create `GradeCutoff` model | `src/models/fes.py` | [x] |
| 3.1.4 | Load `fes_factor_levels.json` into registry | `src/config/fes_factors.py` | [x] |
| 3.1.5 | Load `grade_cutoff_scores.json` into registry | `src/config/fes_factors.py` | [x] |
| 3.1.6 | Implement `get_factor_level_for_grade()` | `src/config/fes_factors.py` | [x] |
| 3.1.7 | Implement `get_does_statements()` | `src/config/fes_factors.py` | [x] |
| 3.1.8 | Write unit tests for FES models | `tests/test_unit_fes.py` | [x] |

#### 3.2 Series-Specific Duty Templates

| ID | Task | File | Status |
|----|------|------|--------|
| 3.2.1 | Create `DutySection` model | `src/models/duties.py` | [x] |
| 3.2.2 | Create `SeriesDutyTemplate` model | `src/models/duties.py` | [x] |
| 3.2.3 | Load `gs2210_major_duties_templates.json` | `src/config/series_templates.py` | [x] |
| 3.2.4 | Implement `get_duty_template(series, grade)` | `src/config/series_templates.py` | [x] |
| 3.2.5 | Implement `validate_duty_weights(sections)` | `src/config/series_templates.py` | [x] |
| 3.2.6 | Write unit tests for duty templates | `tests/test_unit_duties.py` | [x] |

#### 3.3 Requirements Models

| ID | Task | File | Status |
|----|------|------|--------|
| 3.3.1 | Create `DraftRequirement` model | `src/models/requirements.py` | [x] |
| 3.3.2 | Create `DraftRequirements` collection model | `src/models/requirements.py` | [x] |
| 3.3.3 | Implement `get_requirements_for_element()` | `src/models/requirements.py` | [x] |
| 3.3.4 | Implement `get_critical_requirements()` | `src/models/requirements.py` | [x] |
| 3.3.5 | Write unit tests for requirements models | `tests/test_unit_draft.py` | [x] |

#### 3.4 FES Evaluation Node

| ID | Task | File | Status |
|----|------|------|--------|
| 3.4.1 | Implement `evaluate_fes_factors_node` | `src/nodes/evaluate_fes_factors_node.py` | [x] |
| 3.4.2 | Build FESEvaluation from grade + factor cutoffs | `src/nodes/evaluate_fes_factors_node.py` | [x] |
| 3.4.3 | Expand all "does" statements for each factor level | `src/nodes/evaluate_fes_factors_node.py` | [x] |
| 3.4.4 | Store FESEvaluation in state | `src/nodes/evaluate_fes_factors_node.py` | [x] |
| 3.4.5 | Write unit tests for FES evaluation | `tests/test_node_fes.py` | [x] |

#### 3.5 Requirements Gathering Node

| ID | Task | File | Status |
|----|------|------|--------|
| 3.5.1 | Implement `gather_draft_requirements_node` | `src/nodes/gather_draft_requirements_node.py` | [x] |
| 3.5.2 | Lookup series-specific duty template | `src/nodes/gather_draft_requirements_node.py` | [x] |
| 3.5.3 | Generate requirements: each "does" statement must appear | `src/nodes/gather_draft_requirements_node.py` | [x] |
| 3.5.4 | Generate requirements: duty sections within percent_range | `src/nodes/gather_draft_requirements_node.py` | [x] |
| 3.5.5 | Build requirements summary response | `src/nodes/gather_draft_requirements_node.py` | [x] |
| 3.5.6 | Write unit tests for requirements node | `tests/test_node_fes.py` | [x] |

#### 3.6 Draft Models

| ID | Task | File | Status |
|----|------|------|--------|
| 3.6.1 | Create `DraftElement` model | `src/models/draft.py` | [x] |
| 3.6.2 | Add requirement tracking fields to `DraftElement` | `src/models/draft.py` | [x] |
| 3.6.3 | Create `QACheckResult` model | `src/models/draft.py` | [x] |
| 3.6.4 | Create `QAReview` model | `src/models/draft.py` | [x] |
| 3.6.5 | Create `DRAFT_ELEMENTS` list | `src/models/draft.py` | [x] |
| 3.6.6 | Create `PRIMARY_FES_FACTORS` list | `src/models/draft.py` | [x] |
| 3.6.7 | Create `OTHER_SIGNIFICANT_FACTORS` list | `src/models/draft.py` | [x] |
| 3.6.8 | Write unit tests for draft models | `tests/test_unit_draft.py` | [x] |

#### 3.7 Draft Generation Prompts

| ID | Task | File | Status |
|----|------|------|--------|
| 3.7.1 | Create `draft.jinja` unified template | `src/prompts/templates/draft.jinja` | [x] |
| 3.7.2 | Handle narrative style (introduction) | `src/prompts/templates/draft.jinja` | [x] |
| 3.7.3 | Handle factor_narrative style (FES 1-5) | `src/prompts/templates/draft.jinja` | [x] |
| 3.7.4 | Handle predetermined_narrative style (duties) | `src/prompts/templates/draft.jinja` | [x] |
| 3.7.5 | Handle combined_factors style (factors 6-9) | `src/prompts/templates/draft.jinja` | [x] |
| 3.7.6 | Handle interview_based style | `src/prompts/templates/draft.jinja` | [x] |
| 3.7.7 | Create `qa_review.jinja` template | `src/prompts/templates/qa_review.jinja` | [x] |
| 3.7.8 | Single dynamic template approach | `src/prompts/templates/draft.jinja` | [x] |

#### 3.8 Draft Generation Node

| ID | Task | File | Status |
|----|------|------|--------|
| 3.8.1 | Implement `generate_element_node` | `src/nodes/generate_element_node.py` | [x] |
| 3.8.2 | Pass "does" statements as MANDATORY inclusions | `src/nodes/generate_element_node.py` | [x] |
| 3.8.3 | Pass series duty template for major_duties | `src/nodes/generate_element_node.py` | [x] |
| 3.8.4 | Uses dynamic draft.jinja template | `src/nodes/generate_element_node.py` | [x] |
| 3.8.5 | Write tests for generate node | `tests/` | [~] |

#### 3.9 QA Review

| ID | Task | File | Status |
|----|------|------|--------|
| 3.9.1 | Create `qa_review.jinja` template | `src/prompts/templates/qa_review.jinja` | [x] |
| 3.9.2 | Implement `qa_review_node` | `src/nodes/qa_review_node.py` | [x] |
| 3.9.3 | Check: All "does" statements present | `src/nodes/qa_review_node.py` | [x] |
| 3.9.4 | Check: Duty section weights within percent_range | `src/nodes/qa_review_node.py` | [x] |
| 3.9.5 | Implement route_after_qa routing | `src/nodes/qa_review_node.py` | [x] |
| 3.9.6 | Limit 1 rewrite per element | `src/nodes/qa_review_node.py` | [x] |
| 3.9.7 | Write tests for QA node | `tests/` | [~] |

#### 3.10 Revision Handling

| ID | Task | File | Status |
|----|------|------|--------|
| 3.10.1 | Implement `handle_revision_node` | `src/nodes/handle_revision_node.py` | [x] |
| 3.10.2 | Increment `revision_count` on element | `src/nodes/handle_revision_node.py` | [x] |
| 3.10.3 | Store feedback in element | `src/nodes/handle_revision_node.py` | [x] |
| 3.10.4 | Write unit tests for revision handling | `tests/test_unit_draft.py` | [x] |

#### 3.11 Graph Updates

| ID | Task | File | Status |
|----|------|------|--------|
| 3.11.1 | Add `evaluate_fes_factors` node to graph | `src/graphs/main_graph.py` | [x] |
| 3.11.2 | Add `gather_draft_requirements` node to graph | `src/graphs/main_graph.py` | [x] |
| 3.11.3 | Add `generate_element` node to graph | `src/graphs/main_graph.py` | [x] |
| 3.11.4 | Add `qa_review` node to graph | `src/graphs/main_graph.py` | [x] |
| 3.11.5 | Add `handle_revision` node to graph | `src/graphs/main_graph.py` | [x] |
| 3.11.6 | Add conditional edge: interview → FES | `src/graphs/main_graph.py` | [x] |
| 3.11.7 | Add conditional edge: QA → rewrite or present | `src/graphs/main_graph.py` | [x] |
| 3.11.8 | Export updated graph visualization | `output/graphs/` | [x] |

#### 3.12 Integration Testing

| ID | Task | File | Status |
|----|------|------|--------|
| 3.12.1 | Test: FES evaluation for GS-13 | `tests/test_node_fes.py` | [x] |
| 3.12.2 | Test: GS-2210-13 gets duty template | `tests/test_node_fes.py` | [x] |
| 3.12.3 | Test: "does" statements expanded | `tests/test_unit_fes.py` | [x] |
| 3.12.4 | Test: QA catches missing "does" | `tests/` | [~] |
| 3.12.5 | Test: QA catches bad duty weight | `tests/` | [~] |
| 3.12.6 | Test: Full interview → FES → draft flow | `tests/` | [~] |
- Mark tasks `[~]` when in progress
- Mark tasks `[!]` when blocked
- Delete this punch list when MVP is complete
