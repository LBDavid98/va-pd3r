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
# src/models/draft.py - DraftElement
last_qa_content_hash: str | None = Field(
    default=None,
    description="Hash of content at last QA run, for skip-if-unchanged optimization",
)

def compute_content_hash(self) -> str:
    """Compute hash of current content for QA caching."""
    return hashlib.sha256(self.content.encode()).hexdigest()[:16]

def qa_content_unchanged(self) -> bool:
    """Check if content hasn't changed since last QA."""
    if not self.last_qa_content_hash or not self.qa_review:
        return False
    return self.compute_content_hash() == self.last_qa_content_hash

# src/nodes/qa_review_node.py - in _qa_single()
if (
    element.qa_content_unchanged()
    and element.qa_review
    and element.qa_review.passes
):
    logger.info(f"Skipping QA for {element.name}: content unchanged since last pass")
    return idx, element, element.qa_review, 1.0
```

The hash is saved in `apply_qa_review()`:
```python
def apply_qa_review(self, review: QAReview) -> None:
    # Save content hash for caching
    self.last_qa_content_hash = self.compute_content_hash()
    # ... rest of implementation
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

## Related

- Issue 1.4 in [plans/qa_and_heuristic_remediation_plan.md](../plans/qa_and_heuristic_remediation_plan.md)
- [modules/nodes.md](../modules/nodes.md) - qa_review_node documentation
