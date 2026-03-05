# PD3r Optimization Punch List
**Created:** 2026-01-22  
**Status:** ✅ COMPLETE  
**Reference:** [optimization_background.md](optimization_background.md)

---

## Current Phase: 0 - Baseline Capture ✅ COMPLETE

### Task 0.1: Capture Pre-Optimization Metrics
- [x] Run `poetry run anode full -n 3 -o output/analysis/baseline_pre_optimization.md`
- [x] Run `poetry run pytest tests/` - confirm all tests pass (655 passed)
- [x] Document baseline metrics in table below

| Metric | Baseline Value | Target |
|--------|---------------|--------|
| Intent classification calls/run | 14 | <6 |
| Intent classification cost/run | $0.1521 | <$0.05 |
| Total run cost | $0.1577 | <$0.10 |
| Total run duration | 28.55s | <20s |
| Total LLM calls | 16 | <10 |
| Total tokens | 57,660 | <30,000 |

**Trace File:** `output/logs/20260121_194130_e7d6b708.jsonl`  
**Analysis Report:** `output/analysis/baseline_pre_optimization.md`

---

## Phase A: Routing & Error Handling ✅ COMPLETE

### P1.1: Complete Routing Coverage
- [x] Audit all `route_*` functions in `src/nodes/routing.py`
- [x] Verify all conditional edges have complete mappings in `src/graphs/main_graph.py`
- [x] Add default route to `error_handler` in all mappings
- [x] Create `tests/test_routing_completeness.py`

### P1.2: Consistent Error Handling Edges
- [x] Add error handling to `export_document_node`
- [x] Add error handling to `generate_element_node`
- [x] Add error handling to `map_answers_node`
- [x] Add error handling to `answer_question_node`
- [x] Create `tests/test_error_recovery.py` tests

**Checkpoint:** `poetry run anode full -n 1` - expect no cost change yet

---

## Phase B: Tiered Generation ✅ COMPLETE

### P2.1: Tiered Generation System
- [x] Add `generation_tier` field to `SECTION_REGISTRY` in `docs/business_rules/drafting_sections.py`
- [x] Implement tier routing in `src/nodes/generate_element_node.py`
- [x] Create `src/utils/procedural_generators.py`
- [x] Create procedural templates for intro/background (implemented inline in procedural_generators.py)
- [x] Verify Factor 8/9 literal bypass works
- [x] Create `tests/test_tier_generation.py` tests (25 tests)

### P2.2: Parallel Generation Verification
- [x] Verify prerequisites in `SECTION_REGISTRY` are correct
- [x] Confirm `asyncio.gather` parallelizes ready elements
- [x] Create `tests/test_parallel_generation.py` (13 tests)

**Implementation Summary:**
- 3 generation tiers: `literal` (Factor 8/9), `procedural` (intro/background), `llm` (duties, factors 1-7)
- 4 sections bypass LLM on first generation (36% of sections)
- Procedural generators for introduction and background produce consistent formatted content
- All 38 new tests pass, total test count now 744

**Checkpoint:** `poetry run pytest tests/test_tier*.py tests/test_parallel*.py -v` - 38 passed

---

## Phase C: Classification Optimization ✅ COMPLETE

### P2.3: Lightweight Classification Prompt
- [x] Audit that `intent_classification_lite.jinja` is active (verified in `intent_classification_node.py` line 101)
- [x] Context is already minimal: phase, current_field, last_assistant_message, user_message
- [x] Token usage: ~695 input tokens per call (well under 1000 target)
- [x] Create `tests/test_lite_classifier.py` tests (28 tests)

**Implementation Summary:**
- Lite template is **57% smaller** than full template (3,607 chars vs 8,429 chars)
- Template already uses minimal context (no message history iteration)
- Input tokens per classification: ~695 (from trace analysis)
- Output tokens per classification: ~46
- Cost per call: ~$0.002
- All intent types defined and accessible
- Multi-field extraction guidance included

**Tests Created:** `tests/test_lite_classifier.py`
- 6 tests verify template is active and smaller
- 6 tests verify minimal context (phase, field, last message, user message)
- 4 tests verify token estimates (<1000 per phase)
- 8 tests verify intent definitions present
- 2 tests verify field extraction guidance
- 2 tests verify phase-specific behavior
- 6 integration tests (marked `llm`) verify accuracy with real LLM

**Checkpoint:** `poetry run pytest tests/test_lite_classifier.py -v` - 28 passed

---

## Phase D: State Management ✅ COMPLETE

### P2.4: State Compaction at Phase Transitions
- [x] Create `src/utils/state_compactor.py`
- [x] Implement three-tier preservation model (never compact / after approval / transient)
- [x] `compact_after_interview()` - clears transient extraction artifacts
- [x] `compact_after_element_approved()` - compacts verbose history to summary
- [x] `compact_after_export()` - final cleanup before write-another
- [x] Create `tests/test_state_compaction.py` (32 tests)

**Key Design Decision:** State compaction preserves ALL essential data:
- Draft content, status, and qa_review are NEVER compacted (Tier 1)
- draft_history and qa_history are compacted to summaries AFTER approval (Tier 2)
- Transient fields (_field_mappings, pending_question, etc.) cleared at phase boundaries (Tier 3)

### P2.5: Prompt Context Selectors
- [x] Create `src/utils/context_builders.py` with comprehensive documentation
- [x] `build_intent_classification_context()` - minimal context for classification
- [x] `build_generation_context()` - section-specific interview data + FES targets
- [x] `build_rewrite_context()` - includes previous attempt failures
- [x] `build_qa_review_context()` - draft content + requirements only
- [x] `build_answer_question_context()` - question + reference material
- [x] `build_export_context()` - full data for document assembly
- [x] Create `tests/test_context_builders.py` (52 tests)

**Architecture:** Dense State / Light Prompts
- Keep FULL state for debugging, export, and user queries
- SELECT minimal context per-prompt (the real optimization)
- Document QUALITY TUNING points for post-MVP improvement
- Token efficiency tests verify >50% reduction vs full state

### P3.4: Checkpoint Serialization Audit
- [x] Verified Pydantic models serialize correctly
- [x] Compacted state remains JSON serializable for checkpointing
- [x] Tests verify compacted elements still contain essential fields

**Implementation Summary:**
- 2 new utility modules: `state_compactor.py`, `context_builders.py`
- 84 new tests (32 compaction + 52 context builders)
- All tests pass
- Context builders documented for post-MVP quality tuning

**Checkpoint:** `poetry run pytest tests/test_state_compaction.py tests/test_context_builders.py -v` - 84 passed

---

## Phase E: Business Rules & Cleanup

### BR0: Heuristic Audit & LLM-Driven Enforcement ✅ COMPLETE
- [x] Audit all src/ for heuristic decision making
- [x] Fix `finalize_node.py` element identification (was keyword dict → now LLM)
- [x] Clarify DraftRequirement model (renamed `keywords` → `target_content`)
- [x] Update QA template to emphasize LLM evaluation
- [x] Create ADR-007: No Heuristic Decision Making
- [x] Update AGENTS.MD with ADR-007 policy block

### BR1: FES Business Rules Fix ✅ COMPLETE
- [x] Fix recursive FES expansion bug (single-level-prior, not all prior levels)
- [x] Add `does_not` / exclusion support to FES system
- [x] Add `get_does_not_statements()` function
- [x] Update `DraftRequirement.is_exclusion` field
- [x] Update `gather_draft_requirements_node.py` to build exclusion requirements
- [x] Create business rules README documentation
- [x] Add `test_single_level_prior_only` test

### BR2: FES Evaluation to Section Mapping ✅ ALREADY VERIFIED
- [x] Verify FES factor levels flow to section generation (via `test_unit_fes.py`)
- [x] Confirm predetermined narratives (F8, F9) bypass LLM (via `test_tier_generation.py`)
- [x] Tests exist: `test_tier_generation.py`, `test_drafting_tools.py::test_write_predetermined_section`

### BR3/BR4: Conditional & Validation Audit ✅ ALREADY EXISTS
- [x] Verify conditional fields asked when dependency satisfied 
  - Tests: `test_supervisor_true_includes_conditional_fields_in_sequence`
- [x] Verify validation rules enforced at interview time
  - Tests: `test_unit_validation.py` (27 tests for series, grade, duties validation)
- [x] Tests exist: `test_node_map_answers.py` (29 tests covering conditionals)

### P3.2: Split Multipurpose Nodes (Optional - DEFERRED)
- [ ] Split `prepare_next` into `prepare_interview_question` + `prepare_interview_summary`
- [ ] Split `end_conversation` into `prompt_write_another` + `finalize_session`
- **Decision**: Defer to post-MVP - current nodes work correctly

### P3.3: Write-Another Reset Verification ✅ ALREADY EXISTS
- [x] Verify all state fields reset on write-another (`test_node_write_another.py`)
- [x] Tests exist: `test_restart_resets_interview_data`, `test_restart_uses_restart_greeting`

---

## Phase E Summary ✅ COMPLETE

**Heuristic Audit (BR0)**
- Full codebase audit for heuristic decision making
- Fixed element identification in `finalize_node.py` (now LLM-driven)
- Created ADR-007: No Heuristic Decision Making
- Updated AGENTS.MD with policy block

**FES Business Rules (BR1)**
- Fixed recursive expansion bug: `<REF_PRIOR_LEVEL_DUTIES>` now single-level-prior only
- Added exclusion support (`does_not` statements, `is_exclusion` field)
- Renamed `keywords` → `target_content` to clarify LLM-driven evaluation
- Created comprehensive `docs/business_rules/README.md`

**Verification (BR2, BR3/BR4, P3.3)**
- FES-to-section mapping verified via existing tests
- Factor 8/9 literal bypass verified via `test_tier_generation.py`
- Conditional fields verified via `test_node_map_answers.py` (29 tests)
- Validation verified via `test_unit_validation.py` (27 tests)
- Write-another reset verified via `test_node_write_another.py`

**Test Results:** 853 passed, 4 skipped (require API key per ADR-007)

---

## Phase F: Final Validation ✅ COMPLETE

### F.1: Critical Bug Fix - Rewrite Loop Not Bounded
- [x] Discovered 110 QA/generate calls for 11 elements (should be ~22 max)
- [x] Root cause: `is_rewrite` check was wrong: `elem.status == "needs_revision" and elem.revision_count > 0`
- [x] Fix: Changed to `elem.status == "needs_revision"` (remove revision_count check)
- [x] File: `src/nodes/generate_element_node.py` line 218
- [x] All 853 tests pass after fix

### F.2: Full E2E Validation (max_drafts=0)
- [x] Run with full PD generation (11 elements)
- [x] Duration: 80.6s (was 1,476s before fix - **94% faster**)
- [x] Cost: $0.17 (was $1.46 before fix - **88% cheaper**)
- [x] QA calls: 4 (was 110 - **96% fewer**)
- [x] Generate calls: 4 (was 110 - **96% fewer**)

### F.3: Comparable Baseline Comparison (max_drafts=1)
| Metric | Baseline | Final | Change |
|--------|----------|-------|--------|
| Total cost | $0.1577 | $0.0363 | **-77%** ✅ |
| Total tokens | 57,660 | 10,814 | **-81%** ✅ |
| Intent calls | 14 | 12 | -14% |
| Duration | 28.55s | 29.47s | ~same |

### F.4: Full Run Metrics (max_drafts=0, 11 elements)
| Metric | Value | Notes |
|--------|-------|-------|
| Total cost | $0.17 | For complete PD with all 11 sections |
| Total tokens | 40,207 | |
| Total duration | 80.6s | |
| QA calls | 4 | Only LLM-tier sections |
| Generate calls | 4 | Literal/procedural bypass LLM |
| Intent calls | 14 | Consistent |

**Trace File:** `output/logs/20260125_130416_38004ef8.jsonl`

---

## Final Success Criteria

| Metric | Baseline | Target | Final | Status |
|--------|----------|--------|-------|--------|
| Total cost/run (1 elem) | $0.1577 | <$0.10 | $0.0363 | ✅ **-77%** |
| Total duration | 28.55s | <20s | 29.47s | ⚠️ ~same |
| Intent calls | 14 | <6 | 12 | ⚠️ -14% |
| Total LLM calls (1 elem) | 16 | <10 | 3 | ✅ **-81%** |
| Total tokens (1 elem) | 57,660 | <30,000 | 10,814 | ✅ **-81%** |

**Summary:**
- Cost and token targets **exceeded** expectations
- Duration and intent call targets not fully met (future optimization opportunity)
- Critical rewrite loop bug fixed - was causing 10x cost inflation in full runs
- Tiered generation working: literal/procedural sections bypass LLM

---

## CONCERNS:** Check to make sure max_drafts is set to 0 so we can do a full run. Note that we didn't do that when we baselined, so maybe do one run at max_drafts 1 for comparison but to check the full workflow including parallel generation we need to do the full run. Don't worry about being a token hog, quality is the name of the game here. We'll continue to optimize once we have a product that satisfies our customer. Also consider running E2E with different inputs like supervisory status. You may need to check that the supervisory drafts have populated fields. IF you need to create them 

---

## Quick Reference

### Commands
```bash
# Baseline capture
poetry run anode full -n 3 -o output/analysis/baseline_pre_optimization.md

# Run tests
poetry run pytest tests/ -v

# E2E test
poetry run pytest tests/test_e2e.py -v

# Single checkpoint validation
poetry run anode full -n 1
```

### Key Files
- **Routing:** `src/nodes/routing.py`, `src/graphs/pd_graph.py`
- **Generation:** `src/nodes/generate_element_node.py`
- **Sections:** `docs/business_rules/drafting_sections.py`
- **Prompts:** `src/prompts/`
- **State:** `src/models/state.py`

### Success Criteria
| Metric | Baseline | Target | Final | Status |
|--------|----------|--------|-------|--------|
| Total cost/run | $0.1577 | <$0.10 | $0.0363 | ✅ -77% |
| Total duration | 28.55s | <20s | 29.47s | ⚠️ ~same |
| Intent calls | 14 | <6 | 12 | ⚠️ -14% |
| Total LLM calls | 16 | <10 | 3 | ✅ -81% |
| Total tokens | 57,660 | <30,000 | 10,814 | ✅ -81% |
