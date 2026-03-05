# QA Node & Heuristic Remediation Plan

**Created:** 2026-01-25  
**Status:** READY FOR IMPLEMENTATION  
**Priority:** HIGH  
**Estimated Effort:** 2-3 days  

---

## Executive Summary

Two analysis reports identified critical issues requiring remediation:

1. **QA Review Node Analysis** - The `qa_review_node` has bugs causing inconsistent state transitions and unused confidence thresholds
2. **Heuristic Audit** - One remaining heuristic violation and one questionable pattern need LLM-driven replacements

This plan provides step-by-step instructions for addressing each issue.

---

## Pre-Implementation Checklist

Before starting, verify you have:
- [ ] Read [AGENTS.MD](../../AGENTS.MD) (mandatory)
- [ ] Read [docs/decisions/005-no-mock-llm.md](../decisions/005-no-mock-llm.md)
- [ ] Read [docs/decisions/006-llm-driven-routing.md](../decisions/006-llm-driven-routing.md)
- [ ] Read [docs/decisions/007-no-heuristic-decisions.md](../decisions/007-no-heuristic-decisions.md)
- [ ] Working `.env` with `OPENAI_API_KEY`
- [ ] Run `poetry install` to ensure dependencies are current
- [ ] Run `poetry run pytest -q` to establish baseline (all tests should pass)

---

## Part 1: QA Review Node Fixes

### Issue 1.1: CRITICAL - "qa_passed without qa_review" State Corruption

**Location:** [src/nodes/qa_review_node.py](../../src/nodes/qa_review_node.py) lines 137-158

**Problem:**  
In `_qa_single()`, when there are no requirements for an element, the code sets `element.status = "qa_passed"` directly WITHOUT calling `element.apply_qa_review()`. This creates inconsistent state where:
- `element.status == "qa_passed"` 
- `element.qa_review == None`
- `element.requirements_checked == 0`

This violates our invariant: **every status transition should go through `apply_qa_review()`**.

**Current Code (lines 137-158):**
```python
async def _qa_single(idx: int):
    element = DraftElement.model_validate(draft_elements[idx])

    # Handle no requirements cases
    if not requirements:
        element.status = "qa_passed"  # ❌ BUG: Direct status set, no apply_qa_review()
        return idx, element, QAReview(
            passes=True,
            check_results=[],
            overall_feedback="No requirements to check",
            needs_rewrite=False,
            suggested_revisions=[],
        ), 1.0

    element_reqs = requirements.get_requirements_for_element(element.name)
    if not element_reqs:
        element.status = "qa_passed"  # ❌ BUG: Same problem
        return idx, element, QAReview(...), 1.0
```

**Fix Instructions:**

1. Open [src/nodes/qa_review_node.py](../../src/nodes/qa_review_node.py)

2. Find the `_qa_single()` function (around line 135)

3. Replace the early-return branches to call `apply_qa_review()`:

```python
async def _qa_single(idx: int):
    element = DraftElement.model_validate(draft_elements[idx])

    # Handle no requirements cases - STILL call apply_qa_review for consistency
    if not requirements:
        qa_review = QAReview(
            passes=True,
            check_results=[],
            overall_feedback="No requirements defined for this draft",
            needs_rewrite=False,
            suggested_revisions=[],
        )
        element.apply_qa_review(qa_review)  # ✅ FIX: Use apply_qa_review
        return idx, element, qa_review, 1.0

    element_reqs = requirements.get_requirements_for_element(element.name)
    if not element_reqs:
        qa_review = QAReview(
            passes=True,
            check_results=[],
            overall_feedback=f"No specific requirements for {element.display_name}",
            needs_rewrite=False,
            suggested_revisions=[],
        )
        element.apply_qa_review(qa_review)  # ✅ FIX: Use apply_qa_review
        return idx, element, qa_review, 1.0
```

4. **Add invariant assertion** after the `asyncio.gather()` call (around line 190):

```python
results = await asyncio.gather(*[_qa_single(idx) for idx in ready_indices])

# Invariant: Every reviewed element must have qa_review populated
for idx, element, qa_review, _ in results:
    assert element.qa_review is not None, (
        f"BUG: Element {element.name} has status {element.status} "
        f"but qa_review is None. This violates our state consistency invariant."
    )
```

**Verification:**
```bash
poetry run pytest tests/test_node_* -v -k "qa"
```

---

### Issue 1.2: CRITICAL - Confidence Thresholds Not Enforced

**Location:** [src/nodes/qa_review_node.py](../../src/nodes/qa_review_node.py) lines 30-31, 180-188

**Problem:**  
The constants `QA_PASS_THRESHOLD = 0.8` and `QA_REWRITE_THRESHOLD = 0.5` are defined but **never used**. The node relies entirely on the LLM's `overall_passes` boolean, which may not align with our defined thresholds.

**Current Code (around line 180):**
```python
qa_review = _convert_schema_to_model(result)
overall_conf = result.overall_confidence

element.apply_qa_review(qa_review)  # Uses LLM's passes, ignores thresholds
```

**Fix Instructions:**

1. Create a new function to enforce thresholds (add after `_convert_schema_to_model`):

```python
def _enforce_confidence_thresholds(
    schema_result: QAReviewSchema,
    element_reqs: list,
) -> tuple[QAReview, bool, bool]:
    """
    Enforce deterministic pass/fail based on confidence thresholds.
    
    This overrides the LLM's overall_passes with our defined rules:
    - Fail if ANY critical requirement failed
    - Fail if overall_confidence < QA_PASS_THRESHOLD
    - Trigger rewrite if overall_confidence < QA_REWRITE_THRESHOLD
    
    Args:
        schema_result: Raw LLM output
        element_reqs: Requirements for joining is_critical flag
        
    Returns:
        Tuple of (QAReview, passes, needs_rewrite)
    """
    # Build requirement lookup for is_critical
    req_by_id = {r.id: r for r in element_reqs}
    
    # Check for critical failures
    critical_failed = False
    for check in schema_result.check_results:
        req = req_by_id.get(check.requirement_id)
        if req and req.is_critical and not check.passed:
            critical_failed = True
            break
    
    # Determine pass/fail based on our thresholds
    confidence = schema_result.overall_confidence
    
    if critical_failed:
        passes = False
        needs_rewrite = True
    elif confidence < QA_PASS_THRESHOLD:
        passes = False
        needs_rewrite = confidence < QA_REWRITE_THRESHOLD
    else:
        passes = True
        needs_rewrite = False
    
    # Override LLM's decisions with our deterministic rules
    check_results = [
        QACheckResult(
            requirement_id=r.requirement_id,
            passed=r.passed,
            explanation=r.explanation,
            severity=r.severity,
            suggestion=r.suggestion,
        )
        for r in schema_result.check_results
    ]
    
    qa_review = QAReview(
        passes=passes,  # Our decision, not LLM's
        check_results=check_results,
        overall_feedback=schema_result.overall_feedback,
        needs_rewrite=needs_rewrite,  # Our decision
        suggested_revisions=schema_result.suggested_revisions,
    )
    
    return qa_review, passes, needs_rewrite
```

2. Update the LLM call block in `_qa_single()` to use this function:

```python
try:
    result, _usage = await traced_structured_llm_call(
        llm=llm,
        prompt=prompt,
        output_schema=QAReviewSchema,
        node_name=f"qa_review:{element.name}",
        metadata={"element": element.name},
    )
    
    # Apply deterministic thresholds (not just LLM's opinion)
    qa_review, passes, needs_rewrite = _enforce_confidence_thresholds(
        result, element_reqs
    )
    overall_conf = result.overall_confidence
    
    # Log if we overrode the LLM's decision
    if passes != result.overall_passes:
        logger.info(
            f"QA threshold override for {element.name}: "
            f"LLM said passes={result.overall_passes}, "
            f"thresholds say passes={passes} (conf={overall_conf:.2f})"
        )
        
except Exception as e:
    # ... existing error handling ...
```

**Verification:**
```bash
# Run QA-specific tests
poetry run pytest tests/test_qa_tools.py tests/test_node_* -v -k "qa"
```

---

### Issue 1.3: HIGH - Add Concurrency Limiting

**Location:** [src/nodes/qa_review_node.py](../../src/nodes/qa_review_node.py) line 189

**Problem:**  
`asyncio.gather(*[_qa_single(idx) for idx in ready_indices])` runs unlimited concurrent LLM calls. With many ready elements, this risks rate limits and spiky latency.

**Fix Instructions:**

1. Add semaphore at module level (after the constants):

```python
import asyncio
from contextlib import asynccontextmanager

# Concurrency control for parallel QA
QA_CONCURRENCY_LIMIT = 4
_qa_semaphore: asyncio.Semaphore | None = None

def _get_qa_semaphore() -> asyncio.Semaphore:
    """Get or create the QA semaphore for the current event loop."""
    global _qa_semaphore
    if _qa_semaphore is None:
        _qa_semaphore = asyncio.Semaphore(QA_CONCURRENCY_LIMIT)
    return _qa_semaphore
```

2. Wrap the LLM call in `_qa_single()` with semaphore:

```python
async def _qa_single(idx: int):
    element = DraftElement.model_validate(draft_elements[idx])
    
    # ... early returns for no requirements ...
    
    context = _build_qa_context(element, requirements)
    template = jinja_env.get_template("qa_review.jinja")
    prompt = template.render(**context)
    
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    
    # Limit concurrent LLM calls
    sem = _get_qa_semaphore()
    async with sem:
        try:
            result, _usage = await traced_structured_llm_call(
                llm=llm,
                prompt=prompt,
                output_schema=QAReviewSchema,
                node_name=f"qa_review:{element.name}",
                metadata={"element": element.name},
            )
            # ... rest of processing ...
```

---

### Issue 1.4: MEDIUM - Content Hash Caching (Cost Optimization)

**Location:** [src/models/draft.py](../../src/models/draft.py) `DraftElement` class

**Problem:**  
QA re-runs on unchanged content, wasting LLM calls.

**Fix Instructions:**

1. Add hash field to `DraftElement` in [src/models/draft.py](../../src/models/draft.py):

```python
import hashlib

class DraftElement(BaseModel):
    # ... existing fields ...
    
    # Content hash for QA caching
    last_qa_content_hash: str | None = Field(
        default=None,
        description="Hash of content at last QA run, for skip-if-unchanged optimization"
    )
    
    def compute_content_hash(self) -> str:
        """Compute hash of current content for QA caching."""
        return hashlib.sha256(self.content.encode()).hexdigest()[:16]
    
    def qa_content_unchanged(self) -> bool:
        """Check if content hasn't changed since last QA."""
        if not self.last_qa_content_hash or not self.qa_review:
            return False
        return self.compute_content_hash() == self.last_qa_content_hash
```

2. Update `apply_qa_review()` to store the hash:

```python
def apply_qa_review(self, review: QAReview) -> None:
    """Apply QA review results and save to history."""
    # Save content hash for caching
    self.last_qa_content_hash = self.compute_content_hash()
    
    # ... rest of existing implementation ...
```

3. In [src/nodes/qa_review_node.py](../../src/nodes/qa_review_node.py), skip QA for unchanged passing content:

```python
async def _qa_single(idx: int):
    element = DraftElement.model_validate(draft_elements[idx])
    
    # Skip QA if content unchanged and previously passed
    if (element.qa_content_unchanged() and 
        element.qa_review and 
        element.qa_review.passes):
        logger.info(f"Skipping QA for {element.name}: content unchanged since last pass")
        return idx, element, element.qa_review, 1.0
    
    # ... rest of function ...
```

---

## Part 2: Heuristic Violations

### Issue 2.1: ❌ VIOLATION FIXED - Element Identification in finalize_node.py

**Status:** ALREADY FIXED ✅

Per the code review, [src/nodes/finalize_node.py](../../src/nodes/finalize_node.py) has already been updated to use LLM-based element extraction via `_extract_target_element()`. The old keyword dictionary approach was removed.

**Verification only:**
```bash
# Ensure no keyword dict remains
grep -n "element_keywords" src/nodes/finalize_node.py
# Should return nothing

# Run the finalize node tests
poetry run pytest tests/ -v -k "finalize"
```

---

### Issue 2.2: ⚠️ QUESTIONABLE - parse_approval_response() Heuristics

**Location:** [src/tools/human_tools.py](../../src/tools/human_tools.py) lines 322-365

**Problem:**  
Uses keyword matching to parse approval responses:
```python
if response_lower in ('approve', 'approved', 'looks good', 'lgtm', 'ok', 'yes', 'proceed'):
    return {"action": "approve", "feedback": None}
```

**Risk Level:** LOW-MEDIUM  
This parses explicit commands, not ambiguous intent. However, nuanced responses like "I think it's mostly fine but..." would be misclassified.

**Recommended Fix:** Replace with LLM interpretation for better UX.

**Fix Instructions:**

1. Create new schema for approval interpretation in [src/tools/human_tools.py](../../src/tools/human_tools.py):

```python
from pydantic import BaseModel, Field
from src.utils.llm import traced_structured_llm_call

class ApprovalInterpretation(BaseModel):
    """LLM structured output for interpreting approval responses."""
    
    action: Literal["approve", "revise", "reject", "question", "change"] = Field(
        description="The user's intended action"
    )
    confidence: float = Field(
        ge=0, le=1,
        description="Confidence in this interpretation"
    )
    feedback: str | None = Field(
        default=None,
        description="Any feedback or additional context from the user"
    )
    field: str | None = Field(
        default=None,
        description="For 'change' action: the field to modify"
    )
    value: str | None = Field(
        default=None,
        description="For 'change' action: the new value"
    )
    reasoning: str = Field(
        description="Brief explanation of interpretation"
    )
```

2. Create async interpretation function:

```python
async def _interpret_approval_response(
    response: str,
    context: str = "section approval",
) -> ApprovalInterpretation:
    """
    Use LLM to interpret user's approval response.
    
    Per ADR-007: All ambiguous user input must be LLM-interpreted.
    """
    import os
    from langchain_openai import ChatOpenAI
    from src.exceptions import ConfigurationError
    
    if not os.getenv("OPENAI_API_KEY"):
        raise ConfigurationError(
            "OPENAI_API_KEY required for response interpretation"
        )
    
    prompt = f"""Interpret the user's response to a {context} request.

User's response: "{response}"

Determine their intent:
- "approve": They want to accept/proceed (yes, ok, looks good, approve, lgtm, proceed)
- "revise": They want changes but keep the general content (revise, update, change this part)
- "reject": They want to start over completely (no, reject, rewrite, start over)
- "question": They're asking a question, not making a decision
- "change": They want to change a specific field to a specific value (change X to Y)

For "change" actions, extract the field name and new value if present.
Include any feedback or context they provided.

Be generous with approval interpretation - if they seem positive, interpret as approve.
"""

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    result, _ = await traced_structured_llm_call(
        llm=llm,
        prompt=prompt,
        output_schema=ApprovalInterpretation,
        node_name="interpret_approval",
        metadata={"response": response[:100]},
    )
    
    return result
```

3. Update `parse_approval_response()` to use async version:

```python
def parse_approval_response(response: str) -> dict[str, Any]:
    """Parse a human's approval response into structured data.
    
    Uses LLM interpretation for nuanced understanding.
    Falls back to basic parsing only for extremely clear cases.
    """
    import asyncio
    
    response_lower = response.lower().strip()
    
    # Fast path for unambiguous single-word responses (optimization only)
    if response_lower in ('approve', 'approved', 'yes', 'ok', 'lgtm'):
        return {"action": "approve", "feedback": None}
    if response_lower in ('reject', 'no'):
        return {"action": "reject", "feedback": None}
    
    # For anything else, use LLM interpretation
    try:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Already in async context
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(
                        asyncio.run, 
                        _interpret_approval_response(response)
                    ).result()
            else:
                result = loop.run_until_complete(
                    _interpret_approval_response(response)
                )
        except RuntimeError:
            result = asyncio.run(_interpret_approval_response(response))
        
        return {
            "action": result.action,
            "feedback": result.feedback,
            "field": result.field,
            "value": result.value,
        }
    except Exception as e:
        # Log but don't fail - return as question for clarification
        logger.warning(f"Failed to interpret approval response: {e}")
        return {"action": "question", "feedback": response}
```

**Verification:**
```bash
poetry run pytest tests/test_interview_tools.py tests/test_human_tools.py -v
```

---

### Issue 2.3: Documentation Update - Misleading Field Names

**Location:** [src/models/requirements.py](../../src/models/requirements.py)

**Status:** ALREADY FIXED ✅

Per the code review, the field has already been renamed from `keywords` to `target_content` with backward-compatible alias. The docstring has been updated to clarify these are "LLM context, not grep patterns."

**Verification only:**
```bash
# Check the field definition
grep -A5 "target_content" src/models/requirements.py
```

---

## Part 3: Documentation Updates

### 3.1: Update nodes.md for QA Node

**Location:** [docs/modules/nodes.md](../modules/nodes.md) around line 145

Add after the `qa_review_node` description:

```markdown
#### `qa_review_node` (Detailed)

**Confidence Thresholds:**
- `QA_PASS_THRESHOLD = 0.8`: Sections must have ≥80% confidence to pass
- `QA_REWRITE_THRESHOLD = 0.5`: Sections with <50% confidence trigger automatic rewrite

**Threshold Enforcement:**
The node enforces these thresholds deterministically, overriding LLM's `overall_passes` when:
- Any critical requirement failed → `passes = False, needs_rewrite = True`
- `overall_confidence < QA_PASS_THRESHOLD` → `passes = False`
- `overall_confidence < QA_REWRITE_THRESHOLD` → `needs_rewrite = True`

**Caching:**
QA is skipped for elements where:
- Content hash matches `last_qa_content_hash`
- Previous QA passed

**Concurrency:**
Parallel QA limited to `QA_CONCURRENCY_LIMIT = 4` concurrent LLM calls.

**State Invariant:**
Every element with `status in ("qa_passed", "qa_failed", "needs_revision")` MUST have `qa_review != None`.
```

---

### 3.2: Update docs/INDEX.md

**Location:** [docs/INDEX.md](../INDEX.md)

Update the "Last Updated" date and add to Quick Reference:

```markdown
### QA System Constants
```python
# src/nodes/qa_review_node.py
QA_PASS_THRESHOLD = 0.8      # ≥80% confidence to pass
QA_REWRITE_THRESHOLD = 0.5   # <50% triggers rewrite
QA_CONCURRENCY_LIMIT = 4     # Max parallel LLM calls
```
```

---

### 3.3: Create ADR for Content Hash Caching

**Location:** Create [docs/decisions/008-qa-content-caching.md](../decisions/008-qa-content-caching.md)

```markdown
# ADR-008: QA Content Hash Caching

**Date:** 2026-01-25  
**Status:** Accepted  
**Deciders:** David Hook

## Context

QA review runs on every draft element that is "ready", even if the content hasn't changed since the last QA run. In iterative workflows with multiple rewrite cycles, this wastes LLM calls and increases cost.

## Decision

Implement content-hash-based caching for QA:

1. Store `last_qa_content_hash` on each `DraftElement`
2. Before running QA, check if current hash matches stored hash
3. If unchanged AND previous QA passed, skip the LLM call and return cached result

## Implementation

```python
# DraftElement
last_qa_content_hash: str | None = None

def compute_content_hash(self) -> str:
    return hashlib.sha256(self.content.encode()).hexdigest()[:16]

def qa_content_unchanged(self) -> bool:
    if not self.last_qa_content_hash or not self.qa_review:
        return False
    return self.compute_content_hash() == self.last_qa_content_hash
```

## Consequences

### Positive
- 20-60% reduction in QA LLM calls during iterative drafting
- Faster feedback loops when user is only modifying one section
- No behavior change for cold starts or actual content changes

### Negative
- Additional field in state (minimal storage overhead)
- Slightly more complex QA node logic
- Must invalidate cache if requirements change (not just content)

## Future Work

Consider invalidating `last_qa_content_hash` when `draft_requirements` changes, not just when content changes.
```

---

## Implementation Order

Execute tasks in this order for safe incremental progress:

1. **Issue 1.1** - Fix apply_qa_review consistency (CRITICAL, blocks others)
2. **Issue 1.2** - Enforce confidence thresholds (CRITICAL)
3. **Issue 1.3** - Add concurrency limiting (HIGH, quick win)
4. **Issue 2.2** - LLM approval interpretation (MEDIUM, improves UX)
5. **Issue 1.4** - Content hash caching (MEDIUM, cost optimization)
6. **Part 3** - Documentation updates (do after code changes)

After each issue:
```bash
# Run tests
poetry run pytest -q

# If all pass, commit
git add -A && git commit -m "<descriptive message>"
```

---

## Test Coverage Requirements

Before considering this plan complete, ensure:

- [ ] `test_qa_review_no_requirements_still_populates_qa_review` - New test
- [ ] `test_qa_review_confidence_threshold_override` - New test  
- [ ] `test_qa_review_critical_failure_forces_rewrite` - New test
- [ ] `test_qa_review_content_hash_skips_unchanged` - New test
- [ ] `test_approval_interpretation_ambiguous_response` - New test
- [ ] All existing tests in `tests/test_qa_tools.py` still pass
- [ ] All existing tests in `tests/test_node_*.py` still pass

---

## Rollback Plan

If issues arise:
1. `git revert <commit>` for specific changes
2. The changes are isolated - each issue can be reverted independently
3. Content hash caching can be disabled by setting `last_qa_content_hash = None` always

---

## Success Criteria

- [ ] No "qa_passed with qa_review=None" states possible
- [ ] Confidence thresholds are enforced in logs (check with `PD3R_TRACING=true`)
- [ ] QA concurrency limited (monitor with trace analysis)
- [ ] `parse_approval_response` uses LLM for non-trivial inputs
- [ ] All documentation reflects actual behavior
- [ ] All tests pass
