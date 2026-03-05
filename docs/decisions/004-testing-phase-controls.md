# ADR-004: Testing Phase Controls (STOP_AT / SKIP_QA)

## Status
Accepted

## Context
During development, we need to iteratively test and fine-tune specific phases of the PD3r workflow:

1. **Interview Phase Testing** - We're currently fine-tuning the interview and question-answering loop. Running through the full draft/review/export cycle after each interview test is wasteful and makes debugging harder.

2. **Draft Phase Testing** - Once interview is stable, we'll need to test drafting without repeatedly running through QA review cycles.

Testing the full pipeline end-to-end is valuable, but during focused development on specific phases, we need surgical controls to isolate behavior.

## Decision
Add two configuration flags to control testing flow:

### `STOP_AT: str | None`
Stop execution at a specific phase and route directly to END.

**Valid values**: `"interview"`, `"requirements"`, `"drafting"`, `"review"`, `None` (disabled)

**Behavior**:
- When `STOP_AT="interview"`: After `check_interview_complete` marks phase as `requirements`, route to `end_conversation` instead of continuing
- The stop happens at the *transition point* after the phase completes, before the next phase begins

### `SKIP_QA: bool`
Skip the QA review loop during drafting phase.

**Default**: `False`

**Behavior**:
- When `True`: After `generate_element`, skip `qa_review` and go directly to user presentation
- Useful for testing draft generation without QA overhead

## Implementation

### Configuration Location
Add to `src/constants.py` as module-level constants with defaults from environment:

```python
import os

# Testing phase controls
STOP_AT: str | None = os.environ.get("PD3R_STOP_AT", None)
SKIP_QA: bool = os.environ.get("PD3R_SKIP_QA", "").lower() in ("true", "1", "yes")
```

### Routing Integration
Modify `route_by_intent` or add a wrapper function that checks STOP_AT before returning the normal route:

```python
def _maybe_stop_at_phase(phase: str, normal_route: RouteDestination) -> RouteDestination:
    """Check if we should stop at this phase instead of continuing."""
    if STOP_AT and phase == STOP_AT:
        return "end_conversation"
    return normal_route
```

### Key Integration Points
1. **After interview complete**: In `_route_requirements_phase`, when intent is `confirm` and we'd normally go to `evaluate_fes`, check STOP_AT
2. **After drafting complete**: In `route_after_advance_element`, when we'd transition to `finalize`
3. **After QA review**: In `route_after_qa`, optionally skip to user presentation

## Consequences

### Positive
- Enables focused testing of individual phases
- Reduces test cycle time during development
- Makes debugging easier by isolating phase behavior
- Easy to disable (set to None/False or unset env vars)

### Negative
- Additional complexity in routing logic
- Risk of forgetting to disable before production (mitigated by defaulting to disabled)
- May mask integration bugs between phases

### Mitigations
- Log warnings when STOP_AT or SKIP_QA are enabled
- Add validation that these are only enabled in non-production environments
- E2E tests should always run with both disabled

## Current Usage (2026-01-16)
- `STOP_AT="interview"` - Active while fine-tuning interview and question loop
- `SKIP_QA=False` - Not yet needed
