# Phase E: Business Rules Deep Dive Analysis
**Created:** 2026-01-25  
**Status:** ANALYSIS COMPLETE - AWAITING APPROVAL  
**Reference:** [optimization_punch_list.md](optimization_punch_list.md)

---

## Executive Summary

This analysis addresses two key concerns before Phase E implementation:

1. **FES "Preceding Level" Logic Bug**: Currently recursive (1-8 includes ALL of 1-7, 1-6, 1-5...), should only include ONE level prior per HR guidance.

2. **Maintainability**: How easy is it to update/add draft elements and amend them based on customer feedback?

### Key Finding: The JSON is Actually Correct (Mostly)

The `fes_factor_levels.json` data structure is **well-designed**. Each level explicitly lists its own unique "does" statements, plus `<REF_PRIOR_LEVEL_DUTIES>` as a marker. The **bug is in the Python code** that interprets this marker recursively.

---

## Current Architecture Analysis

### What We Have

```
┌─────────────────────────────────────────────────────────────────┐
│                    DATA FLOW                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  fes_factor_levels.json                                         │
│  (9 factors × ~5 levels each = ~45 level definitions)           │
│         │                                                        │
│         ▼                                                        │
│  src/config/fes_factors.py                                      │
│  _expand_does_statements() ← BUG: Recursive expansion           │
│         │                                                        │
│         ▼                                                        │
│  FESEvaluation model (src/models/fes.py)                        │
│  .does = [21 statements for Level 1-8!]                         │
│         │                                                        │
│         ▼                                                        │
│  gather_draft_requirements_node.py                              │
│  Creates 1 DraftRequirement per "does" statement                │
│         │                                                        │
│         ▼                                                        │
│  QA Review ← CONFUSING: 21 checks for Factor 1 alone!           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### The Problem in Numbers

For a GS-13 with Factor 1 Level 1-8:
- **Current behavior**: 21 "does" statements (recursive expansion)
- **Correct behavior**: 5 statements (level 1-7 + 4 unique level-8 items)

Per HR guidance: "1-8 says include all of 1-7" means **only 1 level back**, not recursively to 1-1.

### Why This Matters

1. **QA Confusion**: The QA reviewer sees requirements like "Understands very simple office procedures" for a GS-13 senior position - this is confusing and wrong.

2. **Prompt Bloat**: 21 requirements vs 5 = 4x token usage for Factor 1 alone.

3. **False Failures**: QA might flag a senior data scientist PD for not mentioning "filing" because that's in Level 1-1.

---

## Proposed Fix: Single-Level Prior Reference

### Option A: Fix in Python (RECOMMENDED)

Change `_expand_does_statements()` from recursive to single-level:

```python
# BEFORE (recursive - wrong)
def _expand_does_statements(factor_num: int, target_level: Union[int, str]) -> list[str]:
    result = []
    for statement in does_list:
        if statement == "<REF_PRIOR_LEVEL_DUTIES>":
            prior_level = _get_prior_level(factor_num, target_level)
            if prior_level is not None:
                result.extend(_expand_does_statements(factor_num, prior_level))  # RECURSIVE!
        else:
            result.append(statement)
    return result

# AFTER (single level - correct)
def _expand_does_statements(factor_num: int, target_level: Union[int, str]) -> list[str]:
    result = []
    for statement in does_list:
        if statement == "<REF_PRIOR_LEVEL_DUTIES>":
            prior_level = _get_prior_level(factor_num, target_level)
            if prior_level is not None:
                # Get ONLY the prior level's unique statements (no further recursion)
                result.extend(_get_level_unique_statements(factor_num, prior_level))
        else:
            result.append(statement)
    return result

def _get_level_unique_statements(factor_num: int, level: Union[int, str]) -> list[str]:
    """Get ONLY the unique statements for a level, excluding the REF marker."""
    # ... returns statements that are NOT "<REF_PRIOR_LEVEL_DUTIES>"
```

**Pros:**
- Single point of change
- JSON data remains unchanged (already correct structure)
- Easy to explain to HR
- Tests can verify exactly N statements per level

**Cons:**
- None significant

### Option B: Change JSON Data (NOT RECOMMENDED)

Pre-expand all levels in JSON so each level has explicit statements.

**Why Not:**
- JSON would be massive (redundant data)
- Harder to maintain
- Doesn't match how HR documents work

---

## Maintainability Analysis

### Current State: GOOD Foundation

| Component | Location | Ease of Update |
|-----------|----------|----------------|
| FES Levels | `docs/business_rules/fes_factor_levels.json` | ✅ Easy - plain JSON |
| Grade Cutoffs | `docs/business_rules/grade_cutoff_scores.json` | ✅ Easy - plain JSON |
| Section Registry | `docs/business_rules/drafting_sections.py` | ✅ Easy - Python dict |
| Intake Fields | `docs/business_rules/intake_fields.py` | ✅ Easy - Pydantic models |
| Duty Templates | `docs/business_rules/gs2210_major_duties_templates.json` | ✅ Easy - JSON |
| Predetermined Narratives | `docs/business_rules/drafting_sections.py` | ✅ Easy - Python dict |

### What Makes It Maintainable

1. **Single Source of Truth**: Each business rule type has ONE authoritative file
2. **Human-Readable Formats**: JSON and Python dicts, not binary or compiled
3. **Separation of Concerns**: Data files separate from processing logic
4. **Good Test Coverage**: 856 tests to catch regressions

### Improvement Opportunities

| Issue | Impact | Fix Complexity |
|-------|--------|----------------|
| Recursive FES expansion | HIGH - causes QA confusion | LOW - ~20 lines |
| No validation schema for JSON | MEDIUM - typos possible | LOW - add JSON schema |
| No "last modified" tracking | LOW - audit trail | TRIVIAL - git already has this |

---

## Recommended Phase E Implementation

### Step 1: Fix the Recursive Bug (Priority: CRITICAL)

**Files to Modify:**
- `src/config/fes_factors.py` - Fix `_expand_does_statements()`

**Tests to Add:**
- `test_single_level_prior_expansion` - Verify only 1 level back
- `test_level_8_does_count` - Should be ~5, not 21

### Step 2: Verify FES → Section Flow (Priority: HIGH)

**Audit:**
- Confirm each FES factor level correctly maps to section requirements
- Verify predetermined narratives (Factor 8/9) bypass correctly
- Document the field flow for each section

### Step 3: Add JSON Schema Validation (Priority: MEDIUM)

**New Files:**
- `docs/business_rules/schemas/fes_factor_levels.schema.json`
- `docs/business_rules/schemas/grade_cutoffs.schema.json`

**Benefit:** Catch typos and structural errors in business rule JSON before runtime.

### Step 4: Conditional Fields Audit (Priority: MEDIUM)

**Verify:**
- `is_supervisor` triggers supervisory fields
- Conditional intake fields asked at right time
- Validation rules enforced at interview time

---

## Test Plan

### New Tests Needed

```python
# tests/test_fes_single_level.py

def test_factor_1_level_8_single_prior():
    """Level 1-8 should include only 1-7's unique statements, not 1-1 through 1-6."""
    does = get_does_statements(1, 8)
    
    # Should have: 4 unique 1-8 + statements from 1-7 ONLY
    # Should NOT have: Level 1-1 statements like "Understands very simple office procedures"
    assert "Understands very simple office procedures" not in does
    assert len(does) <= 10  # Much less than current 21

def test_factor_1_level_7_single_prior():
    """Level 1-7 should include only 1-6's unique statements."""
    does = get_does_statements(1, 7)
    # Similar verification

def test_level_1_no_prior():
    """Level 1 should have no prior reference - just its own statements."""
    does = get_does_statements(1, 1)
    assert len(does) == 2  # Only the 2 unique level-1 statements
```

### Existing Tests to Update

Some existing tests may assume the recursive behavior. We should:
1. Run tests first to see what breaks
2. Update test expectations to match correct behavior

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking existing tests | HIGH | LOW | Update test expectations |
| QA starts passing incorrectly | LOW | MEDIUM | Add explicit requirement count tests |
| Customer confusion from changed output | LOW | LOW | New behavior is more correct |

---

## Questions for You Before Implementation

1. **Confirm the HR rule**: "Include previous level" means **exactly one level back**, correct? Not recursive?

2. **FES Factors 6-9**: These use different level formats (6 uses 1-4, 7 uses a-d, 8-9 use 8-1/9-1). Should the single-level-prior rule apply to all of them?

3. **Predetermined Narratives**: Currently Factor 8 and 9 have fixed text. Are these correct as-is, or do we need level-specific variations?

4. **Validation Strictness**: For customer feedback updates, should we add a "version" field to track business rule changes?

---

## Next Steps (Pending Approval)

- [ ] Confirm approach with user
- [ ] Implement single-level-prior fix in `fes_factors.py`
- [ ] Update tests to reflect correct behavior
- [ ] Run full test suite to catch regressions
- [ ] Add JSON schema validation (optional, recommend)
- [ ] Update punch list with completion status
