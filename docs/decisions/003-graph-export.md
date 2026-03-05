# ADR-003: Auto-export Graph PNG with Timestamp

## Status
Accepted

## Context
Developers need visual feedback on graph structure after changes. Manual export is error-prone and often forgotten.

## Decision
Automatically export the LangGraph workflow to `output/graph.png` after every build and test run. The PNG includes a timestamp in the top-right corner for version tracking. The file is overwritten each run to avoid accumulating stale diagrams.

## Consequences

**Positive:**
- Always-current graph visualization
- Timestamp provides run context
- No manual export step needed
- Single file keeps workspace clean

**Negative:**
- Requires mermaid-cli or fallback
- Adds ~1s to test runs
- Previous versions not preserved (by design)

## Implementation
See `src/graphs/export.py` and `docs/procedures/graph-export.md`.
