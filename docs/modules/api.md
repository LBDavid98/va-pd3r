# API Reference

> Last Updated: 2026-03-05

FastAPI application serving the PD3r agent. Source: `src/api/app.py`, `src/api/websocket.py`, `src/api/models.py`.

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
| `stop` | — | Cancel in-flight processing. |
| `ping` | — | Keep-alive ping (client sends every 30s). |

### Server → Client

| Type | Data | Description |
|------|------|-------------|
| `agent_message` | `{ content, phase?, prompt?, current_field?, missing_fields? }` | Agent response text. `prompt` indicates an interrupt waiting for user input. |
| `state_update` | `SessionState` (partial) | Updated session state after processing completes. |
| `element_update` | `{ name, status, content? }` | Individual draft element status change (defined but not currently sent — elements are fetched via REST). |
| `stopped` | `SessionState` or `{}` | Acknowledgement that processing was cancelled. |
| `error` | `{ message: string }` | Error during processing. |
| `pong` | — | Response to client ping. |

### Typical Flow

```
Client                          Server
  |--- user_message ------------->|
  |                               |  (graph runs)
  |<--- agent_message ------------|  (0..N agent messages)
  |<--- state_update -------------|  (final state snapshot)
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
