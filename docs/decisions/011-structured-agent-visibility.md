# ADR-011: Structured Agent Visibility

**Date:** 2026-03-10
**Status:** Accepted
**Deciders:** David Hook

## Context

Agent internal state was communicated via natural language chat messages ("Let me draft the Introduction...", "Running QA review...", "Do you approve this section?"). The frontend suppressed these with a 138-line regex-based `classifyAgentMessage()` function that pattern-matched on content. This created invisible loops: if the agent asked a question that matched a suppression rule, the user never saw it. Debugging required backend logs.

## Decision

1. **Structured `activity_update` WebSocket messages** replace internal pipeline chat messages as the transport for agent state:
   ```json
   { "type": "activity_update", "data": {
       "activity": "drafting|reviewing|waiting_for_approval|revising|evaluating",
       "element": "Introduction",
       "detail": "optional human-readable detail"
   }}
   ```

2. **Backend derives activity from element status changes** in `_stream_graph()`:
   - `"drafted"` → `"reviewing"` (QA running)
   - `"qa_passed"` → `"waiting_for_approval"`
   - `"needs_revision"` → `"revising"` (auto-rewrite pending)
   - `current_element_name` change → `"drafting"` (new element started)

3. **Frontend renders activity indicators** in ProductPanel (per-element spinner + label like "Drafting...", "Reviewing...") instead of heuristic-based status dots.

4. **`classifyAgentMessage()` reduced to ~28 lines.** Only suppresses:
   - Draft content leaked into chat (shown in ProductPanel instead)
   - FES evaluation detail (shown in ProductPanel)
   - Short pipeline filler lines
   - Interrupt prompts (handled by ProductPanel buttons)

## Consequences

### Positive
- User always sees what the agent is doing — no invisible loops
- Debugging agent issues no longer requires backend logs
- Activity indicator is structured data — can render as progress bar, status line, etc.
- Regex maintenance burden eliminated (138 lines → 28 lines)

### Negative
- Backend must emit activity updates at correct points
- Some nodes may still emit text messages that pass through as "show" (safe fallback)
- Activity derivation adds complexity to `_stream_graph()`

## Related

- [010-backend-authoritative-status.md](010-backend-authoritative-status.md) — Element status
- [architectural_remediation.md](../plans/architectural_remediation.md) — Phase 3
