# Pre-Phase 4 Architecture Refinements Punch List

> **Created**: 2026-01-14  
> **Purpose**: Address design issues identified before Phase 4 implementation  
> **Status**: Not Started  
> **Delete When**: All items complete and merged

---

## Legend

- `[ ]` Not started
- `[~]` In progress
- `[x]` Complete
- `[!]` Blocked / needs discussion

---

## Overview

These refinements improve routing testability, prevent edge-case loops, and ensure phase consistency before the final polish phase.

| # | Issue | Severity | Effort |
|---|-------|----------|--------|
| 1 | Inline lambda routing | ⚠️ Medium | 30 min |
| 2 | `requirements` phase not enforced | ⚠️ Medium | 20 min |
| 3 | `provide_information` unhandled in drafting | 🟡 Low | 10 min |
| 4 | QA rewrite limit split across node/router | 🟡 Low | 15 min |
| 5 | "Write another" flow missing | 🟡 Low | Phase 4 |

---

## 1. Extract Inline Lambda Routing to Named Functions

**Problem**: Inline lambdas in `add_conditional_edges` are untestable and hard to trace.

**Files**: `src/graphs/main_graph.py`, `src/nodes/routing.py`

| ID | Task | File | Status | Notes |
|----|------|------|--------|-------|
| 1.1 | Identify all inline lambdas in `main_graph.py` | `src/graphs/main_graph.py` | [x] | Found 2: handle_draft_response, advance_element |
| 1.2 | Create `route_after_draft_response()` function | `src/nodes/routing.py` | [x] | Checks element status safely |
| 1.3 | Create `route_after_qa()` function (if inline) | `src/nodes/routing.py` | [x] | Already existed, no change needed |
| 1.4 | Create `route_after_advance_element()` function | `src/nodes/routing.py` | [x] | Checks phase for next action |
| 1.5 | Replace lambdas with named functions in graph | `src/graphs/main_graph.py` | [x] | Updated imports and edges |
| 1.6 | Add unit tests for extracted routing functions | `tests/test_unit_routing.py` | [x] | 11 new tests (27 total) |
| 1.7 | Verify graph still exports correctly | `output/graphs/main_graph.mmd` | [x] | Exported, 298 tests pass |

---

## 2. Enforce `requirements` Phase in State Transitions

**Problem**: State model defines `requirements` phase but graph never sets it. Phase can become inconsistent with graph position on interrupts.

**Decision**: Enforce phase use (do not remove).

**Files**: `src/nodes/evaluate_fes_factors_node.py`, `src/nodes/gather_draft_requirements_node.py`

| ID | Task | File | Status | Notes |
|----|------|------|--------|-------|
| 2.1 | Add `phase: "requirements"` to state update in `evaluate_fes_factors_node` | `src/nodes/evaluate_fes_factors_node.py` | [x] | Already present at line 108 |
| 2.2 | Verify `gather_draft_requirements_node` doesn't override phase | `src/nodes/gather_draft_requirements_node.py` | [x] | Sets `phase: "drafting"` correctly at line 260 |
| 2.3 | Add `phase: "drafting"` transition in `generate_element_node` (first call) | `src/nodes/generate_element_node.py` | [x] | Not needed - gather_draft_requirements sets it |
| 2.4 | Update routing to check phase in edge cases | `src/nodes/routing.py` | [x] | Added `_route_requirements_phase()` function |
| 2.5 | Add test for phase transitions | `tests/test_unit_routing.py` | [x] | Added TestRequirementsPhaseRouting + TestPhaseTransitionSequence (7 new tests) |

---

## 3. Handle `provide_information` Intent During Drafting Phase

**Problem**: If user provides unsolicited info during drafting, `route_by_intent` falls through to `user_input`, re-classifying the same input (potential infinite loop).

**Files**: `src/nodes/routing.py`

| ID | Task | File | Status | Notes |
|----|------|------|--------|-------|
| 3.1 | Add `provide_information` case to `_route_drafting_phase()` | `src/nodes/routing.py` | [x] | Routes to `handle_draft_response` as implicit feedback |
| 3.2 | Add `provide_information` case to `_route_review_phase()` | `src/nodes/routing.py` | [x] | Same treatment in review phase |
| 3.3 | Add test case for unsolicited info during drafting | `tests/test_unit_routing.py` | [x] | Added TestDraftingPhaseRouting + TestReviewPhaseRouting classes (10 new tests, 44 total routing tests) |

---

## 4. Consolidate QA Rewrite Limit Logic

**Problem**: Rewrite limit is checked in `qa_review_node.py` but the routing decision happens in router. Split logic is harder to trace.

**Files**: `src/nodes/qa_review_node.py`, `src/nodes/routing.py`

| ID | Task | File | Status | Notes |
|----|------|------|--------|-------|
| 4.1 | Document current rewrite limit behavior | — | [x] | Limit set via `revision_count` on `DraftElement`, checked via `can_rewrite` property |
| 4.2 | Move limit check to `route_after_qa()` function | `src/nodes/routing.py` | [x] | Single source of truth; reads element state directly |
| 4.3 | Update `qa_review_node` to set flag, not make routing decision | `src/nodes/qa_review_node.py` | [x] | Removed `qa_routing` state key; router reads `qa_passed`/`can_rewrite` |
| 4.4 | Add test for rewrite limit edge case | `tests/test_unit_routing.py` | [x] | 7 new tests in `TestRouteAfterQA` class (51 total routing tests) |

---

## 5. "Write Another" Flow (Defer to Phase 4)

**Status**: ✅ **TRANSFERRED** to [implementation_punch_list.md](implementation_punch_list.md) as task 4.3.A

**Problem**: Graph terminates at `end_conversation → END`. No option to start another PD without new session.

~~**Note**: This is already in Phase 4 punch list as task 4.3.1. Deferring.~~

| ID | Task | File | Status | Notes |
|----|------|------|--------|-------|
| 5.1 | Design "write another" state flag | — | [x] | → 4.3.A.1, 4.3.A.2 |
| 5.2 | Add conditional edge from `end_conversation` | `src/graphs/main_graph.py` | [x] | → 4.3.A.6 |
| 5.3 | Update `end_conversation_node` with interrupt | `src/nodes/end_conversation_node.py` | [x] | → 4.3.A.3 |

---

## Completion Checklist

Before starting Phase 4:

- [x] All tests pass: `poetry run pytest -q`
- [x] Graph exports cleanly: check `output/graphs/main_graph.mmd`
- [x] No inline lambdas in `main_graph.py` conditional edges
- [x] Phase transitions documented and tested
- [x] Archive this punch list

---

## References

- [implementation_punch_list.md](implementation_punch_list.md) — Main MVP punch list
- [mvp_implementation_plan.md](mvp_implementation_plan.md) — Full implementation plan
- [src/nodes/routing.py](../../src/nodes/routing.py) — Routing functions
- [src/graphs/main_graph.py](../../src/graphs/main_graph.py) — Graph definition
