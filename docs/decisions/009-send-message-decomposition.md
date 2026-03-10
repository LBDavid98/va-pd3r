# ADR-009: send_message() Decomposition

**Date:** 2026-03-10
**Status:** Accepted
**Deciders:** David Hook

## Context

`SessionManager.send_message()` grew to 173 lines, mixing graph orchestration, message streaming, element change detection with fragile hash comparison, QA result transformation (duplicated between streaming and REST paths), and state extraction. This made it hard to test, debug, and extend.

## Decision

Decompose `send_message()` into orchestration-only code (~67 lines) that delegates to:

1. **`src/api/transforms.py`** — Single source of truth for QA review → frontend summary transformation. Handles both dict (streaming) and Pydantic model (REST) inputs.

2. **`src/api/element_tracker.py`** — `ElementChangeTracker` class with SHA256-based content hashing (replacing the fragile `str(len(content)) + content[:50]` approach). Detects element changes across graph streaming events and emits change notifications only when status or content actually changes.

3. **`_stream_graph()`** — Private method handling the graph streaming loop, message dedup, element change detection, and activity derivation.

4. **`_collect_unstreamed_messages()`** — Collects AI messages not already streamed to the client.

5. **`_update_position_title()`** — Tracks position title changes and persists metadata.

## Principles

- **API methods orchestrate**: validate inputs, delegate to helpers, return results
- **Business logic in dedicated modules**: transforms, trackers, etc.
- **Single source of truth**: one function for each data transformation
- **No duplicate logic**: QA transform used by both streaming and REST paths

## Consequences

### Positive
- Each unit is independently testable (44 new tests for transforms + tracker)
- SHA256 hash detects content changes beyond 50 characters
- QA transform bugs fixed in one place
- `send_message()` reads as a clear orchestration sequence

### Negative
- More files to navigate (transforms.py, element_tracker.py)
- Slight indirection for developers unfamiliar with the decomposition

## Related

- [008-qa-content-caching.md](008-qa-content-caching.md) — QA content hash caching
- [architectural_remediation.md](../plans/architectural_remediation.md) — Phase 1
