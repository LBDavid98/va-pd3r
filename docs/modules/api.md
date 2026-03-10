# API Reference

> Last Updated: 2026-03-10

FastAPI application serving the PD3r agent.

**Source files:**
- `src/api/app.py` — FastAPI app with REST endpoints
- `src/api/websocket.py` — WebSocket handler for streaming chat
- `src/api/models.py` — Request/Response Pydantic models
- `src/api/session_manager.py` — SessionManager wrapping LangGraph graph (orchestration only, see [ADR-009](../decisions/009-send-message-decomposition.md))
- `src/api/transforms.py` — Data transformations (QA review → frontend summary)
- `src/api/element_tracker.py` — Element change detection with SHA256 hashing

## Base URL

- Development: `http://localhost:8000`
- Docker: `http://localhost:8000` (proxied through Vite in dev)

## REST Endpoints

### Sessions

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sessions` | Create a new session. Returns `session_id`, initial `phase`, and greeting `message`. |
| `POST` | `/sessions/seed` | Create a session pre-populated at a specific phase from test fixtures. Body: `{ script_id, phase }`. |
| `GET` | `/sessions/{id}` | Get current session state (phase, collected fields, interview data, FES evaluation). |
| `DELETE` | `/sessions/{id}` | Delete a session and its checkpoint. |
| `POST` | `/sessions/{id}/stop` | Cancel in-flight graph processing. Returns `{ status: "stopped" | "idle" }`. |
| `POST` | `/sessions/{id}/restart` | Restart session from scratch (keeps same session ID). |

### Messages

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sessions/{id}/message` | Send user message, receive agent response. Body: `{ content, field_overrides? }`. Returns `{ messages[], phase, session_state }`. |

### Fields

| Method | Path | Description |
|--------|------|-------------|
| `PATCH` | `/sessions/{id}/fields` | Persist field overrides to checkpoint. Body: `{ field_overrides: { field: value } }`. Used for inline field editing. |

### Draft

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/sessions/{id}/draft` | Get all draft elements with status, content, and QA review results. |

### Export

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/sessions/{id}/export?format=word` | Export document as `.docx` or `.md`. Query param `format`: `"markdown"` (default) or `"word"`. |

### Configuration

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/config` | Check if API key is set, get current base URL. |
| `POST` | `/config` | Set API key and optional base URL at runtime. Body: `{ api_key, base_url? }`. |

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Returns `{ status: "ok", service: "pd3r" }`. |

## WebSocket Protocol

**Endpoint:** `ws://localhost:8000/sessions/{session_id}/stream`

### Client → Server

| Type | Data | Description |
|------|------|-------------|
| `user_message` | `{ content: string, field_overrides?: object }` | Send user input to the agent. |
| `element_action` | `{ element: string, action: "approve"\|"reject"\|"regenerate", feedback?: string }` | Structured element action — bypasses LLM intent classification. See [ADR-010](../decisions/010-backend-authoritative-status.md). |
| `stop` | — | Cancel in-flight processing. |
| `ping` | — | Keep-alive ping (client sends every 30s). |

### Server → Client

| Type | Data | Description |
|------|------|-------------|
| `agent_message` | `{ content, phase?, prompt?, current_field?, missing_fields? }` | Agent response text. `prompt` indicates an interrupt waiting for user input. |
| `state_update` | `SessionState` (partial) | Updated session state after processing completes. |
| `element_update` | `{ name, status, content?, qa_review? }` | Individual draft element status/content change. Backend is authoritative — see [ADR-010](../decisions/010-backend-authoritative-status.md). |
| `activity_update` | `{ activity: string, element?: string, detail?: string }` | Agent activity indicator. Activities: `"drafting"`, `"reviewing"`, `"waiting_for_approval"`, `"revising"`, `"evaluating"`. See [ADR-011](../decisions/011-structured-agent-visibility.md). |
| `done` | — | Signals processing complete; client clears typing indicator and activity. |
| `stopped` | `SessionState` or `{}` | Acknowledgement that processing was cancelled. |
| `error` | `{ message: string }` | Error during processing. |
| `pong` | — | Response to client ping. |

### Typical Flow

```
Client                          Server
  |--- user_message ------------->|
  |                               |  (graph runs)
  |<--- activity_update ----------|  (agent working on element)
  |<--- agent_message ------------|  (0..N agent messages)
  |<--- element_update -----------|  (element status/content change)
  |<--- state_update -------------|  (final state snapshot)
  |<--- done ---------------------|  (processing complete)
  |                               |
  |--- element_action ----------->|  (structured approve/reject/regenerate)
  |<--- activity_update ----------|
  |<--- element_update -----------|
  |<--- done ---------------------|
  |                               |
  |--- ping ---------------------->|
  |<--- pong ---------------------|
```

## Key Pydantic Models

See `src/api/models.py` for full definitions.

- **SessionState**: phase, position_title, collected_fields, missing_fields, interview_data_values, is_supervisor, fes_evaluation, etc.
- **DraftElementSummary**: name, display_name, status, content, locked, qa_review
- **QAReviewSummary**: passes, overall_feedback, checks[], passed_count, failed_count
- **ElementStatus**: `"pending"` | `"drafted"` | `"qa_passed"` | `"approved"` | `"needs_revision"`

## Error Handling

All endpoints return standard HTTP error codes:
- `400` — Invalid request (bad format, unknown script_id)
- `404` — Session not found
- `500` — Internal error (logged to `output/logs/api.log`)

WebSocket errors are sent as `{ type: "error", data: { message } }` and the connection remains open.
