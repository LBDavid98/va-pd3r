# PD3r Optimization Punch List Plan
**Created:** 2026-01-21  
**Status:** PROPOSED  
**Context:** Post-E2E test success, addressing anode analysis findings  
**Scope:** Comprehensive implementation plan with dependencies, testing, and validation

---

## Executive Summary

This plan addresses findings from the comprehensive node analysis (`anode full`) while respecting the project's **UX-first philosophy**. The user has explicitly stated reluctance about pure deterministic routing to save "fractions of a penny per run" if it jeopardizes user experience.

**Key Constraints:**
- All optimizations must preserve or improve conversational quality
- Changes must be testable and measurable
- Each task must account for upstream/downstream dependencies

**Validation Strategy:** Run `anode full -n 3` before AND after implementation phases to quantify improvements.

---

## 0. Baseline Capture (FIRST)

### Task 0.1: Capture Pre-Optimization Metrics
**Purpose:** Establish baseline for comparison  
**Dependencies:** None  
**Downstream:** All optimization tasks

```bash
# Run before starting any work
poetry run anode full -n 3 -o output/analysis/baseline_pre_optimization.md
```

**Metrics to Capture:**
| Metric | Baseline Value | Target |
|--------|---------------|--------|
| Intent classification calls/run | 12 | <6 |
| Intent classification cost/run | $0.032 | <$0.010 |
| Total run cost | $0.037 | <$0.020 |
| Total run duration | 28.55s | <20s |
| LLM calls for predetermined sections | ~2 | 0 |
| Sequential generation calls | ? | Measure |

**Test:** `pytest tests/test_e2e.py -v` must pass before baseline capture

---

## 1. Understanding the Cost Landscape

### Current State (from anode analysis - LIMITED DRAFTING)
| Component | Cost | % of Total | Calls | Notes |
|-----------|------|------------|-------|-------|
| Intent Classification | $0.032158 | 85% | 12 | Consistent per-run |
| QA Review | $0.003752 | 10% | 2 | Scales with sections |
| Element Generation | $0.001800 | 5% | 2 | **DRAFT LIMITER ON** |
| **Total Run** | $0.037713 | 100% | - | - |

### Cost Reality Check

**Current metrics are misleading.** The draft limiter constrains generation to ~2 elements. Once we generate full PDs:

| Component | Current (2 elements) | Full PD (~15 elements) | Notes |
|-----------|---------------------|------------------------|-------|
| Intent Classification | $0.032 | $0.032 | Fixed per run |
| QA Review | $0.004 | ~$0.030 | Scales linearly |
| Element Generation | $0.002 | ~$0.015 | Scales linearly |
| **Total Run** | $0.038 | **~$0.077** | Generation dominates |

**Key Insight:** At full scale, generation + QA will be ~60% of cost. Intent classification becomes ~40%.

### Optimization Priority Shift
With this reality:
1. **Tiered generation** (eliminate LLM for literal/procedural) → High impact at scale
2. **Parallel generation** → Latency reduction, not cost reduction
3. **State/context optimization** → Moderate token savings across all calls
4. **Intent classification** → Still worth optimizing, but not 85% of the problem anymore

---

## 2. Strategic Direction: Dense State / Light Prompts

### Philosophy
- **Dense State**: Keep all data available in state for export, debugging, checkpointing
- **Light Prompts**: Intelligently filter what goes into LLM prompts based on task context
- **Avoid**: Throwing away data to save tokens (hurts debugging & export)
- **Do**: Build context selectively per-prompt

### Implementation Approach
1. **State Schema**: Full `AgentState` with all fields preserved
2. **Prompt Builders**: Task-specific context selectors that pull only relevant fields
3. **Export Layer**: Access to complete state for document assembly
4. **Checkpoints**: Full state for resume, but serialized efficiently

### Generation Strategy (Three Tiers)
```
┌─────────────────────────────────────────────────────────────────┐
│                    GENERATION TIER SYSTEM                        │
├─────────────────────────────────────────────────────────────────┤
│ TIER 1: LITERAL OUTPUT (No LLM)                                  │
│   - Factor 8 (Physical Demands) - predetermined narrative        │
│   - Factor 9 (Work Environment) - predetermined narrative        │
│   - Cost: $0.00 | Latency: <10ms                                │
├─────────────────────────────────────────────────────────────────┤
│ TIER 2: PROCEDURAL CONSTRUCTION (No LLM)                        │
│   - Introduction section (template + interview data)             │
│   - Background section (template + org hierarchy)                │
│   - Boilerplate sections with variable substitution              │
│   - Cost: $0.00 | Latency: <50ms                                │
├─────────────────────────────────────────────────────────────────┤
│ TIER 3: LLM GENERATION (Full prompt)                            │
│   - Factor narratives (1-7) requiring synthesis                  │
│   - Major duties (creative interpretation needed)                │
│   - QA rewrites (context-dependent)                              │
│   - Cost: ~$0.001/section | Latency: 2-4s                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Prioritized Punch List

### CRITICAL - Must Address

#### P1.1: Complete Routing Coverage Complete Routing Coverage
**Problem:** `init` conditional edges only map to `"user_input"` - runtime error risk  
**Anode Finding:** Incomplete route maps create hard failures

**Upstream Dependencies:**
- None

**Downstream Dependencies:**
- P1.2 (Error Handling) - error_handler must be valid route target

```
Changes Required:
1. Audit ALL route_* functions for possible return values
2. Add default route to error_handler in all mappings
3. Convert init to normal edge if truly single-target
4. Add test assertions: all router outputs are covered
```

**Files to Audit:**
- `src/graphs/pd_graph.py` - All `add_conditional_edges` calls
- `src/nodes/routing.py` - All `route_*` functions

**Tests Required:**
- `test_routing_completeness.py` - Assert all route keys are mapped
- `test_routing_default_fallback.py` - Unknown routes → error_handler

---

#### P1.2: Consistent Error Handling Edges
**Problem:** Only `classify_intent` and `qa_review` route to `error_handler`  
**Risk:** Other nodes fail out-of-band without recovery

**Upstream Dependencies:**
- P1.1 (Routing Coverage) - error_handler must be in route maps

**Downstream Dependencies:**
- None (leaf task)

```
Pattern to Apply to ALL LLM/Tool Nodes:
1. Wrap risky operations in try/except
2. Set state["error"] with structured info
3. Return routing key to error_handler
4. error_handler provides recovery UX
```

**Nodes Requiring Update:**
- `export_document_node`
- `generate_element_node`
- `map_answers_node`
- `answer_question_node`
- Any RAG/tool nodes

**Tests Required:**
- `test_error_recovery_export.py` - Export failure → recovery
- `test_error_recovery_generation.py` - Generation failure → recovery
- `test_error_recovery_extraction.py` - Field extraction failure → recovery

---

### HIGH - Strong Value

#### P2.1: Tiered Generation System (Literal + Procedural + LLM)
**Problem:** LLM called for sections with predetermined or template-able content  
**Current:** Factor 8/9 already use `predetermined_narrative` but routing is implicit  
**Goal:** Explicit three-tier system with clear bypass paths

**Upstream Dependencies:**
- Business rules (`drafting_sections.py`) must define tier per section

**Downstream Dependencies:**
- P2.4 (Parallel Generation) - tier affects parallelization strategy
- P4.2 (Business Rules Flow) - tiering is a business rule

**Tier Definitions:**
```python
# In drafting_sections.py SECTION_REGISTRY
"factor_8_physical_demands": {
    "generation_tier": "literal",  # NEW FIELD
    "literal_content_key": "8-1",  # Points to PREDETERMINED_NARRATIVES
    ...
},
"introduction": {
    "generation_tier": "procedural",  # NEW FIELD
    "template": "intro_template.txt",  # String template with {placeholders}
    ...
},
"factor_1_knowledge": {
    "generation_tier": "llm",  # Requires creative synthesis
    ...
}
```

**Implementation:**
```python
def generate_element(element, state):
    tier = SECTION_REGISTRY[element.name].get("generation_tier", "llm")
    
    if tier == "literal":
        return _get_literal_content(element)  # <10ms, $0.00
    elif tier == "procedural":
        return _render_procedural_template(element, state)  # <50ms, $0.00
    else:  # tier == "llm"
        return await _generate_with_llm(element, state)  # 2-4s, ~$0.001
```

**Files to Modify:**
- `docs/business_rules/drafting_sections.py` - Add `generation_tier` to all sections
- `src/nodes/generate_element_node.py` - Implement tier routing
- NEW: `src/utils/procedural_generators.py` - Template rendering logic
- NEW: `docs/business_rules/templates/intro_template.txt` - Introduction template

**Tests Required:**
- `test_tier_literal_generation.py` - Factor 8/9 bypass LLM
- `test_tier_procedural_generation.py` - Template rendering works
- `test_tier_llm_generation.py` - Creative sections still use LLM
- `test_tier_output_quality.py` - All tiers produce valid content

**Procedural Template Example (Introduction):**
```
The {position_title}, {series}-{grade}, serves as a key member of the 
{organization_hierarchy[-1]} within {organization_hierarchy[0]}. 
This position reports to {reports_to} and is responsible for 
{major_duties[0]|lower} and related functions.
{% if is_supervisor %}
As a supervisor, this position oversees {num_supervised} employees, 
dedicating approximately {percent_supervising}% of time to supervisory duties.
{% endif %}
```

---

#### P2.2: True Parallel Generation for Ready Elements
**Problem:** Elements without unmet prerequisites could generate simultaneously  
**Current State:** Code has `asyncio.gather` but may not be fully leveraged  
**Goal:** Maximize parallelism while respecting prerequisites

**Upstream Dependencies:**
- P2.1 (Tiered Generation) - tier affects what can parallelize
- `DraftElement.prerequisites` must be accurately defined

**Downstream Dependencies:**
- QA parallelization (P2.5) - more elements ready = more QA in parallel

**Current Code Analysis:**
```python
# Already in generate_element_node.py:
ready_indices = find_ready_indices(draft_elements)
results = await asyncio.gather(*[_generate_single(idx) for idx in ready_to_generate])
```

**Gap Analysis:**
1. ✅ Parallel execution exists for ready elements
2. ❓ Are prerequisites correctly defined in SECTION_REGISTRY?
3. ❓ Are literal/procedural elements handled before LLM batch?
4. ❓ Is QA also parallelized across elements?

**Prerequisites Mapping (to verify/update):**
```python
SECTION_PREREQUISITES = {
    # Tier 1 - No prerequisites, generate immediately
    "factor_8_physical_demands": [],  # literal
    "factor_9_work_environment": [],  # literal
    
    # Tier 2 - Procedural, needs interview data only
    "introduction": [],  # procedural - interview_data available at drafting start
    "background": [],    # procedural
    
    # Tier 3 - LLM, may have inter-section dependencies
    "duties_overview": [],  # can start immediately
    "factor_1_knowledge": [],  # can start immediately
    "factor_2_supervisory_controls": [],
    "factor_3_guidelines": [],
    "factor_4_complexity": [],
    "factor_5_scope_effect": [],
    "factor_6_7_contacts": [],
}
```

**Optimization Strategy:**
```
Phase 1 (Instant): Generate all Tier 1 (literal) sections - ~0ms total
Phase 2 (Fast): Generate all Tier 2 (procedural) sections - ~50ms total
Phase 3 (Parallel LLM): Generate all Tier 3 sections in parallel - ~4s total (not 4s × N)
```

**Files to Modify:**
- `docs/business_rules/drafting_sections.py` - Verify/update prerequisites
- `src/nodes/generate_element_node.py` - Optimize generation order by tier
- `src/models/draft.py` - Ensure `find_ready_indices` respects tiers

**Tests Required:**
- `test_parallel_generation_all_ready.py` - Elements without prereqs parallelize
- `test_parallel_generation_respects_prereqs.py` - Dependencies honored
- `test_parallel_generation_tier_ordering.py` - Literal → Procedural → LLM
- `test_parallel_generation_timing.py` - Verify actual parallelism (not serial)

---

#### P2.3: Lightweight Classification Prompt
**Problem:** Full context sent to classifier (conversation history + draft + requirements)  
**Already Partially Done:** `intent_classification_lite.jinja` exists (82% size reduction)

**Upstream Dependencies:**
- None

**Downstream Dependencies:**
- None

```
Verification Steps:
1. Confirm lite template is active in production path
2. Profile: Is it actually being used?
3. Further reduction: Only include last 3 messages + phase indicator
```

**Files:**
- `src/prompts/intent_classification_lite.jinja`
- `src/nodes/intent_classification_node.py`

**Tests Required:**
- `test_lite_classifier_active.py` - Verify lite template in use
- `test_lite_classifier_accuracy.py` - Accuracy matches full classifier

---

#### P2.4: State Compaction at Phase Transitions
**Problem:** State grows with every turn - prompts get bloated  
**LangGraph Best Practice:** Clean state at phase boundaries

**Upstream Dependencies:**
- None

**Downstream Dependencies:**
- P2.5 (Context Selectors) - compaction affects what's available

```
Compaction Points:
1. interview_complete → requirements
   - Clear: raw extraction artifacts, per-turn debug fields
   - Keep: canonical InterviewData, minimal conversation context

2. element_approved → next_element
   - Clear: verbose QA critiques, intermediate drafts, chain-of-thought
   - Keep: final element content, pass/fail metadata

3. export_complete → write_another OR end
   - Clear: per-element prompts, QA internals, requirements details
   - Keep: document path, export metadata
```

**Implementation:**
- NEW: `src/utils/state_compactor.py`
- Integrate into transition nodes or create dedicated cleanup nodes

**Tests Required:**
- `test_state_compaction_interview_complete.py`
- `test_state_compaction_element_approved.py`
- `test_state_compaction_export_complete.py`
- `test_state_compaction_preserves_essentials.py` - Nothing needed is lost

---

#### P2.5: Prompt Context Selectors
**Problem:** Prompts receive more context than needed  
**Goal:** Each prompt gets exactly what it needs, nothing more

**Upstream Dependencies:**
- P2.4 (State Compaction) - selectors work on compacted state

**Downstream Dependencies:**
- None

```python
Context Selector Pattern:
def build_generation_context(state: AgentState, section_id: str) -> dict:
    """Build minimal context for element generation"""
    section_config = SECTION_REGISTRY[section_id]
    required_fields = section_config["requires"]
    
    return {
        "interview_data": {k: v for k, v in state.interview_data.dict().items() 
                          if k in required_fields},
        "factor_targets": state.fes_evaluation.factors.get(section_id) if "factor" in section_id else None,
        "qa_context": None,  # Only populated for revision prompts
    }
```

**Files:**
- NEW: `src/utils/context_builders.py`
- Update all nodes that call LLMs

**Tests Required:**
- `test_context_selector_minimal.py` - Only required fields included
- `test_context_selector_complete.py` - All required fields present
- `test_context_selector_by_section.py` - Section-specific context correct

---

### MEDIUM - Quality of Life

#### P3.1: Parallel QA Review
**Problem:** QA runs sequentially even when multiple elements are ready  
**Opportunity:** If generation parallelizes, QA should too

**Upstream Dependencies:**
- P2.2 (Parallel Generation) - more elements ready for QA

**Downstream Dependencies:**
- None

**Current Flow:**
```
generate_element(A) → qa_review(A) → user_approval(A) → generate_element(B) → ...
```

**Optimized Flow:**
```
generate_element(A,B,C) in parallel → qa_review(A,B,C) in parallel → present_all → user_approval_batch
```

**Files to Modify:**
- `src/nodes/qa_review_node.py` - Parallelize QA for multiple elements
- `src/graphs/pd_graph.py` - Adjust flow for batch presentation

**Tests Required:**
- `test_qa_parallel_execution.py` - Multiple elements QA'd simultaneously
- `test_qa_parallel_timing.py` - Verify actual parallelism

---

#### P3.2: Split Multipurpose Nodes
**Problem:** `prepare_next` does both interview progression AND summary/confirmation  
**Problem:** `end_conversation` both prompts "write another" AND ends

**Upstream Dependencies:**
- None

**Downstream Dependencies:**
- P3.4 (Write-Another Reset) - cleaner separation

```
Split prepare_next into:
- prepare_interview_question
- prepare_interview_summary

Split end_conversation into:
- prompt_write_another
- finalize_session
```

**Impact:** Cleaner testing, easier reasoning, better separation of concerns

**Files to Modify:**
- `src/nodes/prepare_next_node.py` - Split logic
- `src/nodes/end_conversation_node.py` - Split logic
- `src/graphs/pd_graph.py` - Update edges

**Tests Required:**
- `test_prepare_interview_question.py`
- `test_prepare_interview_summary.py`
- `test_prompt_write_another.py`
- `test_finalize_session.py`

---

#### P3.3: Write-Another Reset Verification
**Problem:** Old state might leak when starting new PD  
**Anode Warning:** Common bug - leaving behind old `draft_elements`

**Upstream Dependencies:**
- None

**Downstream Dependencies:**
- None

```
Verification Checklist for init_node:
- [ ] interview_data reset to empty
- [ ] fes_evaluation reset to None
- [ ] draft_requirements reset
- [ ] draft_elements reset to []
- [ ] current_element reset
- [ ] export selections reset
- [ ] revision flags reset
- [ ] error state reset
- [ ] messages cleared (fresh conversation)
```

**Test to Add:**
- `test_write_another_state_isolation.py` - Full isolation between PDs

---

#### P3.4: Checkpoint Serialization Audit
**Problem:** Pydantic v2 models need careful serialization  
**Risk:** Large blobs (docx bytes) in checkpoints

**Upstream Dependencies:**
- P2.4 (State Compaction) - less to serialize

**Downstream Dependencies:**
- None

```
Audit Points:
1. Pydantic models using model_dump() for serialization
2. Document content stored as file paths, not bytes
3. Checkpoint size monitoring in tests
```

**Tests Required:**
- `test_checkpoint_serialization.py` - State serializes/deserializes
- `test_checkpoint_size_reasonable.py` - Size < threshold (e.g., 100KB)

---

## 4. Business Rules Flow Inspection

### Current Architecture
```
intake_fields.py → InterviewData → FES Evaluation → Draft Requirements → Section Generation
                                                                              ↓
                                                     drafting_sections.py ← (SECTION_REGISTRY)
```

### Inspection Tasks

#### BR1: Trace Field Flow Through Prompts
**Purpose:** Verify each section receives exactly what `SECTION_REGISTRY.requires` specifies

**Upstream Dependencies:**
- None (audit task)

**Downstream Dependencies:**
- P2.5 (Context Selectors) - findings inform selector implementation

For each section in `SECTION_REGISTRY`:
1. Identify `requires` fields
2. Trace where those fields come from in state
3. Verify prompts receive correct context
4. Check: Are we sending MORE than `requires` specifies?

**Sections to Trace:**
| Section | Requires | Data Source | Tier |
|---------|----------|-------------|------|
| introduction | position_title, organization_hierarchy, reports_to | interview_data | procedural |
| background | organization_hierarchy, position_title, series, grade | interview_data | procedural |
| duties_overview | major_duties, daily_activities | interview_data | llm |
| factor_1_knowledge | factor_targets, factor_context | fes_evaluation | llm |
| factor_2_supervisory | factor_targets, factor_context | fes_evaluation | llm |
| factor_3_guidelines | factor_targets, factor_context | fes_evaluation | llm |
| factor_4_complexity | factor_targets, factor_context | fes_evaluation | llm |
| factor_5_scope_effect | factor_targets, factor_context | fes_evaluation | llm |
| factor_6_7_contacts | factor_targets, factor_context | fes_evaluation | llm |
| factor_8_physical | factor_targets | N/A (literal) | literal |
| factor_9_environment | factor_targets | N/A (literal) | literal |

**Tests Required:**
- `test_field_flow_introduction.py` - Introduction gets required fields
- `test_field_flow_factors.py` - Factors get FES data correctly
- `test_field_flow_no_excess.py` - No fields beyond `requires` sent

---

#### BR2: FES Evaluation to Section Mapping
**Question:** How do FES factor levels flow into section generation?

**Upstream Dependencies:**
- FES evaluation node must produce correct structure

**Downstream Dependencies:**
- P2.1 (Tiered Generation) - FES data needed for factors 1-7

```
Current Flow (to verify):
1. fes_evaluation.factors["factor_1"] = {"level": "1-4", "points": 550}
2. SECTION_REGISTRY["factor_1_knowledge"].requires = ["factor_targets", "factor_context"]
3. Prompt receives: factor level definition + interview context
```

**Inspection Points:**
- Is `factor_context` correctly derived from interview data?
- Do predetermined narratives (factors 8, 9) bypass LLM correctly?
- Are factor level definitions loaded from `fes_factor_levels.json`?
- Are `does` statements correctly populated from factor levels?

**Tests Required:**
- `test_fes_to_section_factor_1.py` - Factor 1 data flows correctly
- `test_fes_predetermined_factor_8.py` - Factor 8 uses literal
- `test_fes_predetermined_factor_9.py` - Factor 9 uses literal
- `test_fes_does_statements.py` - Does statements populated

---

#### BR3: Conditional Field Handling
`intake_fields.py` supports `IntakeFieldConditional`:
```python
"conditional": {
    "depends_on": "is_supervisor",
    "value": True
}
```

**Upstream Dependencies:**
- Interview field collection must respect conditionals

**Downstream Dependencies:**
- Section generation for supervisory content

**Verify:**
- Conditional fields only asked when dependency satisfied
- Conditional field values flow correctly to sections that need them
- Supervisory sections only generated when `is_supervisor == True`

**Tests Required:**
- `test_conditional_supervisory_fields.py` - Supervisor fields asked when applicable
- `test_conditional_skip_non_supervisor.py` - Non-supervisor skips supervisor fields
- `test_conditional_sections_generated.py` - Supervisory sections included/excluded correctly

---

#### BR4: Validation Rules Through Export
**Question:** Do OPM validation rules in intake fields get enforced at export?

**Upstream Dependencies:**
- Validation utilities must be connected to export

**Downstream Dependencies:**
- None (terminal validation)

```
Example from intake_fields.py:
"grade": {
    "validation": {
        "choices": ["1", "2", "3", ..., "15"],
        "opm_standard": "OPM General Schedule"
    }
}
```

**Verify:**
- Validation applied at interview time
- Invalid values caught before reaching drafting
- Export doesn't produce documents with invalid field values

**Tests Required:**
- `test_validation_grade_choices.py` - Invalid grade rejected
- `test_validation_series_format.py` - Series format enforced
- `test_validation_export_integrity.py` - Export only with valid data

---

#### BR5: Procedural Template Validation
**New Task for Tiered Generation**

**Purpose:** Ensure procedural templates produce valid PD content

**Upstream Dependencies:**
- P2.1 (Tiered Generation) - templates must exist

**Downstream Dependencies:**
- QA review (if templates produce content that fails QA)

**Verify:**
- Templates exist for all `generation_tier: procedural` sections
- Templates have all required placeholders
- Rendered output meets OPM formatting standards
- No placeholder variables left unsubstituted

**Tests Required:**
- `test_procedural_template_exists.py` - All procedural sections have templates
- `test_procedural_template_placeholders.py` - All placeholders defined
- `test_procedural_template_rendering.py` - Templates render correctly
- `test_procedural_template_no_leftovers.py` - No {unsubstituted} placeholders

---

## 5. Implementation Phases

### Phase 0: Baseline
**Goal:** Establish metrics baseline before any changes

| Task | Duration | Output |
|------|----------|--------|
| Run `anode full -n 3` | 10min | `baseline_pre_optimization.md` |
| Run `pytest tests/` | 5min | All tests pass |
| Document current metrics | 30min | Metrics table populated |

**Exit Criteria:**
- [ ] Baseline report saved
- [ ] All tests passing
- [ ] Metrics documented

---

### Phase A: Routing & Error Handling
**Goal:** Eliminate runtime routing errors, normalize error recovery

| Task | Dependencies | Tests |
|------|--------------|-------|
| P1.1 - Audit all route_* functions | None | Audit doc |
| P1.1 - Add default routes to all mappings | Audit | `test_routing_completeness.py` |
| P1.2 - Add error handling to export_document | P1.1 | `test_error_recovery_export.py` |
| P1.2 - Add error handling to generate_element | P1.1 | `test_error_recovery_generation.py` |
| P1.2 - Add error handling to map_answers | P1.1 | `test_error_recovery_extraction.py` |

**Exit Criteria:**
- [ ] All conditional edges have complete mappings
- [ ] All LLM nodes route to error_handler on failure
- [ ] All new tests pass
- [ ] E2E test still passes

**Checkpoint:** Run `anode full -n 1` - expect no change in costs yet

---

### Phase B: Tiered Generation
**Goal:** Eliminate LLM calls for literal/procedural sections

| Task | Dependencies | Tests |
|------|--------------|-------|
| P2.1 - Add `generation_tier` to SECTION_REGISTRY | None | Schema validation |
| P2.1 - Implement tier routing in generate_element | Tier schema | `test_tier_routing.py` |
| P2.1 - Create procedural templates for intro/background | Tier routing | `test_procedural_templates.py` |
| P2.1 - Verify Factor 8/9 literal bypass | Tier routing | `test_tier_literal.py` |
| P2.2 - Verify parallel generation works | P2.1 | `test_parallel_timing.py` |

**Exit Criteria:**
- [ ] Factor 8/9 generate without LLM calls
- [ ] Introduction/background use templates
- [ ] All ready elements generate in parallel
- [ ] E2E test still passes

**Checkpoint:** Run `anode full -n 3` - expect 2-4 fewer LLM calls per run

---

### Phase C: Classification Optimization
**Goal:** Reduce classification overhead through prompt optimization

| Task | Dependencies | Tests |
|------|--------------|-------|
| P2.3 - Audit lite classifier usage | None | Trace analysis |
| P2.3 - Verify lite template active in production | Audit | `test_lite_classifier_active.py` |
| P2.3 - Reduce context to last 3 messages + phase | Active | `test_lite_classifier_context.py` |
| P2.3 - Profile accuracy vs full classifier | Reduced context | `test_lite_classifier_accuracy.py` |

**Exit Criteria:**
- [ ] Lite classifier confirmed active in all paths
- [ ] Context reduced to minimal necessary
- [ ] Accuracy validated against full classifier
- [ ] E2E test still passes

**Checkpoint:** Run `anode full -n 3` - expect reduced tokens per classification call

> **Future Consideration:** If further cost reduction needed, consider fine-tuning a smaller model (e.g., gpt-4o-mini) specifically for intent classification. This would require collecting classification examples from production runs and is tracked separately from this punch list.

---

### Phase D: State Management
**Goal:** Optimize state for prompts and checkpoints

| Task | Dependencies | Tests |
|------|--------------|-------|
| P2.4 - Implement state_compactor.py | None | Unit tests |
| P2.4 - Add compaction at phase transitions | Compactor | `test_state_compaction.py` |
| P2.5 - Implement context_builders.py | P2.4 | Unit tests |
| P2.5 - Update nodes to use context selectors | Builders | `test_context_minimal.py` |
| P3.4 - Checkpoint audit | P2.5 | `test_checkpoint_size.py` |

**Exit Criteria:**
- [ ] State compacted at each phase transition
- [ ] Prompts receive minimal context
- [ ] Checkpoint sizes reasonable
- [ ] E2E test still passes

**Checkpoint:** Run `anode full -n 3` - expect reduced prompt sizes

---

### Phase E: Business Rules & Cleanup
**Goal:** Verify business rules flow, clean up architecture

| Task | Dependencies | Tests |
|------|--------------|-------|
| BR1 - Field flow audit | None | Audit doc |
| BR2 - FES → Section mapping verification | BR1 | `test_fes_to_section.py` |
| BR3/BR4 - Conditional and validation audit | BR2 | `test_conditionals.py` |
| P3.2 - Node splitting (if time permits) | None | Unit tests |
| P3.3 - Write-another reset verification | None | `test_write_another.py` |

**Exit Criteria:**
- [ ] All business rules verified flowing correctly
- [ ] Write-another produces clean state
- [ ] All tests pass

---

### Phase F: Final Validation
**Goal:** Comprehensive validation and comparison

| Task | Dependencies | Tests |
|------|--------------|-------|
| Run full E2E suite 3x | All phases | All E2E |
| Run `anode full -n 5` | E2E pass | Final metrics |
| Compare baseline vs final metrics | Anode | Metrics doc |
| Document findings | Comparison | Summary report |
| Update AGENTS.MD and docs | Findings | Docs updated |

**Final Deliverables:**
- [ ] `output/analysis/final_post_optimization.md`
- [ ] Comparison table: baseline vs final
- [ ] Updated documentation
- [ ] All tests passing

---

## 6. Success Metrics

### Cost Metrics (Quantitative)

**Note:** These targets assume full PD generation (~15 elements), not limited test runs.

| Metric | Baseline (2 elem) | Projected (15 elem) | Target | Measurement |
|--------|-------------------|---------------------|--------|-------------|
| Intent classification cost/run | $0.032 | $0.032 | $0.025 | anode report |
| LLM calls for literal sections | 2 | ~4 | 0 | anode report |
| LLM calls for procedural sections | 0 | ~3 | 0 | anode report |
| Generation cost (LLM sections only) | $0.002 | ~$0.015 | ~$0.010 | anode report |
| QA review cost | $0.004 | ~$0.030 | ~$0.025 | anode report |
| **Total run cost** | $0.038 | ~$0.077 | **<$0.060** | anode report |
| Total run duration | 28.55s | ~90s | <60s | E2E test |

**Primary Savings Levers:**
1. Tiered generation: ~$0.015 saved (7 literal/procedural sections skip LLM)
2. Context optimization: ~$0.005 saved (reduced tokens per call)
3. Classification prompt: ~$0.007 saved (lighter context)

### Quality Metrics (Qualitative)
- [ ] All E2E tests pass without modification
- [ ] No increase in user-reported confusion/friction
- [ ] Error recovery works from any node failure
- [ ] Procedural content meets OPM standards

### Technical Metrics
- [ ] No runtime routing errors (complete route coverage)
- [ ] Checkpoint sizes stable/reduced (<100KB per checkpoint)
- [ ] State properly reset on "write another"
- [ ] All business rules flow correctly verified

### Comparison Report Template
```markdown
## Optimization Results

### Before (Baseline)
- Date: YYYY-MM-DD
- Report: baseline_pre_optimization.md
- Intent Classification: X calls, $Y cost
- Total Cost: $Z
- Duration: Ns

### After (Final)
- Date: YYYY-MM-DD
- Report: final_post_optimization.md
- Intent Classification: X calls, $Y cost (-N%)
- Total Cost: $Z (-N%)
- Duration: Ns (-N%)

### Changes Implemented
1. ...
2. ...

### Regressions (if any)
- None / List any
```

---

## 7. Dependency Graph

```
                    ┌─────────────────────────────────────────────────────────────────┐
                    │                     PHASE 0: BASELINE                           │
                    │                   anode full -n 3                               │
                    └─────────────────────────────────────────────────────────────────┘
                                                  │
                    ┌─────────────────────────────┼─────────────────────────────┐
                    │                             │                             │
                    ▼                             ▼                             ▼
           ┌───────────────┐            ┌───────────────┐            ┌───────────────┐
           │     P1.1      │            │     P2.1      │            │     BR1       │
           │   Routing     │            │    Tiered     │            │  Field Flow   │
           │  Coverage     │            │  Generation   │            │    Audit      │
           └───────────────┘            └───────────────┘            └───────────────┘
                    │                             │                             │
                    ▼                             ▼                             ▼
           ┌───────────────┐            ┌───────────────┐            ┌───────────────┐
           │     P1.2      │            │     P2.2      │            │     BR2       │
           │    Error      │◄───────────│   Parallel    │            │  FES→Section  │
           │   Handling    │            │  Generation   │            │   Mapping     │
           └───────────────┘            └───────────────┘            └───────────────┘
                    │                             │                             │
                    └─────────────┬───────────────┘                             │
                                  │                                             │
                    ┌─────────────┴─────────────┐                               │
                    │                           │                               │
                    ▼                           ▼                               ▼
           ┌───────────────┐            ┌───────────────┐            ┌───────────────┐
           │     P2.3      │            │     P2.4      │            │   BR3/BR4     │
           │     Lite      │            │    State      │            │ Conditionals  │
           │  Classifier   │            │  Compaction   │            │  Validation   │
           └───────────────┘            └───────────────┘            └───────────────┘
                                               │                             │
                                               ▼                             │
                                        ┌───────────────┐                     │
                                        │     P2.5      │                     │
                                        │   Context     │◄────────────────────┘
                                        │  Selectors    │
                                        └───────────────┘
                                               │
                    ┌──────────────────────────┼──────────────────────────┐
                    │                          │                          │
                    ▼                          ▼                          ▼
           ┌───────────────┐            ┌───────────────┐            ┌───────────────┐
           │     P3.1      │            │     P3.2      │            │     P3.3      │
           │  Parallel QA  │            │  Node Split   │            │Write Another  │
           └───────────────┘            └───────────────┘            └───────────────┘
                    │                          │                          │
                    └──────────────────────────┼──────────────────────────┘
                                               │
                                               ▼
                                        ┌───────────────┐
                                        │     P3.4      │
                                        │  Checkpoint   │
                                        │    Audit      │
                                        └───────────────┘
                                               │
                                               ▼
                    ┌─────────────────────────────────────────────────────────────────┐
                    │                   PHASE F: FINAL VALIDATION                     │
                    │                     anode full -n 5                             │
                    │                   Compare to Baseline                           │
                    └─────────────────────────────────────────────────────────────────┘
```

---

## 8. Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Procedural templates produce poor quality | Content: Unprofessional PD | Low | QA review still catches issues, human approval required |
| State compaction removes needed data | Export: Missing content | Medium | Test export before/after compaction, keep audit trail |
| Lightweight prompt loses accuracy | UX: Wrong intent classification | Medium | Profile accuracy before deployment, keep full classifier as fallback |
| Error handler inadequate recovery | UX: Confusing error states | Low | Rich error context + clear next steps, test all error paths |
| Parallel generation race conditions | Data: Corrupted state | Low | Proper async handling, state isolation per task |
| Tiered generation inconsistent quality | Content: Some sections better than others | Medium | QA review normalizes quality, user approval required |
| Breaking changes in graph structure | Runtime: Failures | High | Comprehensive test coverage, phased rollout |

---

## 9. Test Coverage Requirements

### Unit Tests (per task)
Each P-task requires dedicated unit tests before merge:
```
tests/
├── test_routing_completeness.py      # P1.1
├── test_error_recovery_*.py          # P1.2
├── test_tier_*.py                    # P2.1
├── test_parallel_*.py                # P2.2
├── test_lite_classifier_*.py         # P2.3
├── test_state_compaction_*.py        # P2.4
├── test_context_*.py                 # P2.5
├── test_qa_parallel_*.py             # P3.1
├── test_write_another_*.py           # P3.3
├── test_checkpoint_*.py              # P3.4
├── test_field_flow_*.py              # BR1
├── test_fes_to_section_*.py          # BR2
├── test_conditional_*.py             # BR3
├── test_validation_*.py              # BR4
└── test_procedural_template_*.py     # BR5
```

### Integration Tests
- `test_e2e.py` - Must pass at every phase checkpoint
- `test_integration_foundation.py` - Node interaction tests

### Performance Tests
- `test_parallel_timing.py` - Verify actual parallelism
- `test_checkpoint_size.py` - Size limits

---

## 10. Open Questions

1. **Checkpoint frequency:** Should we checkpoint less often to reduce storage, or keep current frequency for resume reliability?

2. **QA parallelization:** Worth the complexity given current QA cost is only 10%? **Answer needed before Phase E.**

3. **Procedural template scope:** Beyond introduction/background, which other sections could be procedural? What's the quality threshold?

4. **Agent handoff:** Is this plan comprehensive enough to hand off to an agent for execution? If not, what's missing?

---

## 11. Future Considerations (Not In Scope)

### Fine-Tuned Classification Model
If intent classification cost becomes a concern at scale, consider:
- Collecting classification examples from production runs
- Fine-tuning gpt-4o-mini (or similar smaller model) specifically for PD3r intent classification
- Using the fine-tuned endpoint for classification while keeping gpt-4o for generation
- **Estimated effort:** 2-3 weeks including data collection and validation
- **Prerequisite:** Production traffic for training data collection

**This is explicitly NOT part of this punch list.** It's noted here for future reference only.

---

## Appendix A: LangGraph Patterns Referenced

From MCP documentation research:

1. **`pre_model_hook`** - Can filter/trim messages before LLM calls (useful for context selection)
2. **`interrupt()` + `Command(resume=...)`** - Human-in-the-loop pattern we already use
3. **State compaction** - Manage conversation history at phase boundaries
4. **Message filtering** - `RemoveMessage` for pruning old messages
5. **Semantic search in store** - For long-term memory if needed
6. **Parallel execution** - `asyncio.gather` for concurrent tasks (already in use)

---

## Appendix B: Key Files Reference

### State & Models
- `src/models/state.py` - AgentState definition
- `src/models/interview.py` - InterviewData, InterviewElement
- `src/models/draft.py` - DraftElement, prerequisites, find_ready_indices

### Nodes
- `src/nodes/intent_classification_node.py` - Classification logic
- `src/nodes/generate_element_node.py` - Already has parallel generation
- `src/nodes/prepare_next_node.py` - Candidate for splitting
- `src/nodes/user_input_node.py` - Human input handling

### Business Rules
- `docs/business_rules/drafting_sections.py` - SECTION_REGISTRY, PREDETERMINED_NARRATIVES
- `docs/business_rules/intake_fields.py` - RAW_INTAKE_FIELDS
- `docs/business_rules/fes_factor_levels.json` - Factor level definitions ("does" statements)

### Prompts
- `src/prompts/intent_classification_lite.jinja` - Lightweight classifier
- `src/prompts/templates/draft.jinja` - Supports predetermined_narrative style
- `src/prompts/*.jinja` - All prompt templates

---

## Appendix C: Existing Parallel Generation Code

Already implemented in `src/nodes/generate_element_node.py`:

```python
# Find all elements ready for generation
ready_indices = find_ready_indices(draft_elements)

# Run all ready generations in parallel
results = await asyncio.gather(*[_generate_single(idx) for idx in ready_to_generate])

# Predetermined narrative handling already exists
if section_config_local.get("style") == "predetermined_narrative":
    content_local = context_local.get("predetermined_content", "")
    elem.update_content(content_local, is_rewrite=is_rewrite_local)
    return elem, content_local, is_rewrite_local, True  # True = is_predetermined
```

**Gap:** Need to add `generation_tier` routing to extend beyond just "predetermined_narrative" style.

---

## Appendix D: Procedural Template Design

### Template Format
Use Jinja2 for consistency with existing prompts:
```jinja2
{# templates/procedural/introduction.jinja #}
The {{ position_title }}, {{ series }}-{{ grade }}, serves as a key member of the 
{{ organization_hierarchy[-1] }} within {{ organization_hierarchy[0] }}. 
This position reports to {{ reports_to }} and is responsible for 
{{ major_duties[0]|lower if major_duties else "primary functions" }} and related functions.

{% if is_supervisor %}
As a supervisor, this position oversees {{ num_supervised }} employee(s), 
dedicating approximately {{ percent_supervising }}% of time to supervisory duties.
{% endif %}
```

### Validation Rules
1. All placeholders must be defined in `SECTION_REGISTRY.requires`
2. Output must not contain `{{` or `}}` after rendering
3. Output must be grammatically correct English
4. Output must meet minimum word count (configurable per section)

---

*Plan created from anode analysis review + LangGraph MCP documentation research*
*Updated 2026-01-21 with comprehensive dependencies, testing, and validation*
