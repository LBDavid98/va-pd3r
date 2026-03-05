# Heuristic Audit Report

**Date:** 2026-01-25  
**Status:** ADDRESSED - See [qa_and_heuristic_remediation_plan.md](qa_and_heuristic_remediation_plan.md)  
**Concern:** Project claims to be LLM-driven but contains heuristic decision points

---

## Executive Summary

Audit found **5 areas** where heuristics/pattern-matching are used instead of LLM judgment. Some are **legitimate** (data parsing), others are **violations** of our LLM-driven principle.

---

## ✅ LEGITIMATE: Data Parsing (NOT Violations)

These use pattern matching for **data extraction**, not **decision making**:

### 1. `src/validation.py` - Field Validation
- **What**: Validates series codes (4-digit), grades (1-15), parses organization strings
- **Why OK**: This is format validation, not judgment. "Is 2210 a 4-digit number?" is not a decision.
- **Example**: `re.match(r"^\d{4}$", series)` - checking format, not meaning

### 2. `src/config/fes_factors.py` - Level Code Parsing  
- **What**: Parses level codes like "1-8" into factor/level numbers
- **Why OK**: Pure data extraction from structured format

---

## ⚠️ QUESTIONABLE: Human Response Parsing

### 3. `src/tools/human_tools.py:322-351` - `parse_approval_response()`
```python
if response_lower in ('approve', 'approved', 'looks good', 'lgtm', 'ok', 'yes', 'proceed'):
    return {"action": "approve", "feedback": None}
if response_lower.startswith('change '):
    match = re.match(r'change\s+(\w+)\s+to\s+(.+)', response_lower, re.IGNORECASE)
```

**Status**: BORDERLINE  
**Rationale**: This is parsing explicit human commands, not interpreting ambiguous input.  
**Risk**: Low - but could miss nuanced responses like "I think it's fine but..."
**Recommendation**: Consider LLM interpretation for better UX, but not critical.

---

## ✅ FIXED VIOLATIONS

### 4. `src/nodes/finalize_node.py` - Element Identification from Feedback

**Status**: ✅ FIXED (2026-01-25)  
**Solution**: Replaced keyword dictionary with LLM-based `_extract_target_element()` function using `ElementExtractionResult` schema.  
**Verification**: `grep -n "element_keywords" src/nodes/finalize_node.py` returns nothing.

### 5. `src/models/requirements.py` - Misleading Field Names

**Status**: ✅ FIXED (2026-01-25)  
**Solution**: 
- Renamed `keywords` → `target_content` with backward-compatible alias
- Updated docstrings to clarify "LLM context, not grep patterns"
- `check_type` docstring updated to explain it's a hint for LLM evaluation approach

---

## ⚠️ REMAINING: parse_approval_response() Heuristics

**Location:** [src/tools/human_tools.py](../../src/tools/human_tools.py) lines 322-365

```python
if response_lower in ('approve', 'approved', 'looks good', 'lgtm', 'ok', 'yes', 'proceed'):
    return {"action": "approve", "feedback": None}  
**Actual Behavior**: QA template passes keywords to LLM as "things to look for" - LLM decides.
**Risk**: Confuses developers, suggests non-LLM evaluation
**Fix Required**: Rename fields to clarify they're LLM prompts, not matching rules.

---

## Verification: QA System IS LLM-Driven ✅

Traced the QA flow:
1. `gather_draft_requirements_node.py` builds requirements with FES "does" statements
2. Requirements passed to `qa_review.jinja` template
3. Template gives LLM the requirements and asks it to evaluate
4. LLM returns structured judgment (pass/fail/confidence/explanation)
5. **NO keyword matching in Python code** - all evaluation by LLM

The `check_type` and `keywords` fields are **hints to the LLM**, not code-executed checks.

---

## Action Items

### High Priority
1. **Fix `finalize_node.py`**: Replace keyword dict with LLM element extraction
2. **Rename misleading fields**: `keywords` → `target_content`, `check_type` → remove or clarify

### Medium Priority  
3. **Enhance `parse_approval_response()`**: Use LLM for nuanced approval interpretation

### Documentation
4. **Update `docs/business_rules/README.md`**: Clarify that "keywords" are LLM prompts
5. **Add ADR**: Document "no heuristic decision making" principle for QA/routing

---

## Architectural Principle (Proposed ADR-007)

```markdown
# ADR-007: No Heuristic Decision Making

## Context
We claim to be an LLM-driven agent but had heuristic code making decisions.

## Decision
- **Data parsing** (regex for format validation) = OK
- **Decision making** (routing, element identification, QA evaluation) = MUST use LLM
- **Human command parsing** (explicit approve/reject) = Acceptable for clear commands

## Consequences
- All ambiguous user input interpreted by LLM
- QA evaluation always by LLM (no keyword grep)
- Routing by LLM tool selection (already per ADR-006)
```
