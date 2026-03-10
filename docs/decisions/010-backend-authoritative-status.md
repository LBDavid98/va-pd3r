# ADR-010: Backend-Authoritative Element Status

**Date:** 2026-03-10
**Status:** Accepted
**Deciders:** David Hook

## Context

The frontend approve button was optimistically setting element status to "approved" locally before sending the approval as free text for LLM intent classification. This caused state divergence: the frontend showed "approved" immediately, but the backend might reject the approval (e.g., QA failure) or classify the free-text intent differently. Two independent state owners for the same data is an antipattern.

## Decision

1. **Backend is the single source of truth for element status.** The frontend never sets status (approved, needs_revision, etc.) locally. It sends intent and renders whatever the backend confirms.

2. **Structured `element_action` WebSocket protocol** replaces free-text approval. Client sends:
   ```json
   { "type": "element_action", "data": { "element": "introduction", "action": "approve" } }
   ```
   Backend translates to `[ACTION:approve:introduction]` prefix, which the intent classification node short-circuits on (no wasted LLM call).

3. **Frontend shows pending state** (spinner + disabled button) while waiting for backend confirmation via `element_update` message.

4. **Free-text path preserved.** Users can still type "approve the introduction" in chat — it goes through normal LLM intent classification. The structured protocol is for button-driven actions only.

## Implementation

- `websocket.py`: New `element_action` message type handler
- `intent_classification_node.py`: `_ACTION_PREFIX_RE` regex + `_classify_structured_action()` for short-circuit
- `ProductPanel.tsx`: `pendingAction` state, `sendElementAction()` via raw WebSocket, pending spinner
- `useWebSocket.ts`: `wsRef` set in sessionStore for direct WebSocket access

## Consequences

### Positive
- Eliminates state divergence between frontend and backend
- Reduces LLM calls (no classification needed for button actions)
- Approve flow becomes deterministic and testable
- Frontend behavior always matches backend truth

### Negative
- Slight perceived latency (~200-500ms) for approve action — mitigated by pending spinner
- Two approval paths (structured + free-text) must stay in sync

## Related

- [011-structured-agent-visibility.md](011-structured-agent-visibility.md) — Activity updates
- [architectural_remediation.md](../plans/architectural_remediation.md) — Phase 2
