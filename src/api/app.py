"""FastAPI application for PD3r agent.

Provides REST endpoints for session management, messaging, and document export.
WebSocket endpoint for streaming chat is in websocket.py.

Sessions persist across server restarts via SQLite checkpointing.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from src.api.models import (
    AgentMessage,
    CreateSessionResponse,
    DraftElementSummary,
    DraftState,
    LLMConfigRequest,
    LLMConfigResponse,
    PatchFieldsRequest,
    PatchWordCountsRequest,
    SeedSessionRequest,
    SendMessageRequest,
    SendMessageResponse,
    SessionState,
)
from src.api.session_manager import SessionManager
from src.api.websocket import websocket_chat
from src.config.drafting_sections import TARGET_WORD_COUNTS
from src.config.settings import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Module-level reference populated during lifespan
session_manager: SessionManager | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and tear down the session manager with SQLite persistence."""
    global session_manager
    session_manager = await SessionManager.create()
    logger.info("Session manager initialised (SQLite-backed)")
    yield
    await session_manager.close()
    logger.info("Session manager shut down")


app = FastAPI(
    title="PD3r API",
    description="Federal Position Description writing agent API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Session endpoints ---


@app.post("/sessions", response_model=CreateSessionResponse)
async def create_session():
    """Create a new PD3r session and run until the first agent prompt."""
    try:
        session_id, initial = await session_manager.create_session()
        message = _extract_interrupt_message(initial.get("interrupt"))
        return CreateSessionResponse(
            session_id=session_id,
            phase=initial["state"].get("phase", "init"),
            message=message,
        )
    except Exception as e:
        logger.exception("Failed to create session")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sessions/seed", response_model=CreateSessionResponse)
async def create_seeded_session(request: SeedSessionRequest):
    """Create a session pre-populated at a specific phase from test fixtures."""
    try:
        session_id, initial = await session_manager.create_seeded_session(
            script_id=request.script_id,
            phase=request.phase,
        )
        message = _extract_interrupt_message(initial.get("interrupt"))
        return CreateSessionResponse(
            session_id=session_id,
            phase=initial["state"].get("phase", "init"),
            message=message,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to create seeded session")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions/{session_id}", response_model=SessionState)
async def get_session(session_id: str):
    """Get the current state of a session."""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        state = await session_manager.get_session_state(session_id)
        return SessionState(**state)
    except Exception as e:
        logger.exception("Failed to get session state")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    if not await session_manager.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted"}


@app.post("/sessions/{session_id}/stop")
async def stop_session(session_id: str):
    """Stop any in-flight processing for a session."""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    was_running = await session_manager.stop_session(session_id)
    return {"status": "stopped" if was_running else "idle"}


@app.post("/sessions/{session_id}/restart")
async def restart_session(session_id: str):
    """Stop processing and restart the session from scratch."""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        session_id, initial = await session_manager.restart_session(session_id)
        message = _extract_interrupt_message(initial.get("interrupt"))
        return CreateSessionResponse(
            session_id=session_id,
            phase=initial["state"].get("phase", "init"),
            message=message,
        )
    except Exception as e:
        logger.exception("Failed to restart session")
        raise HTTPException(status_code=500, detail=str(e))


def _extract_interrupt_message(interrupt: object) -> str:
    """Extract a display message from an interrupt value."""
    if isinstance(interrupt, str):
        return interrupt
    if isinstance(interrupt, dict):
        return interrupt.get("prompt") or interrupt.get("message") or "Session created"
    return "Session created"


# --- Field override endpoints ---


@app.patch("/sessions/{session_id}/fields")
async def patch_fields(session_id: str, request: PatchFieldsRequest):
    """Immediately persist field overrides to the session checkpoint.

    Called by the frontend when the user edits an interview field inline.
    The overrides are applied to interview_data in the LangGraph checkpoint
    so all subsequent graph turns see the updated values.
    """
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        config = session_manager._config_for(session_id)
        await session_manager._apply_field_overrides(config, request.field_overrides)
        return {"status": "ok", "fields_updated": list(request.field_overrides.keys())}
    except Exception as e:
        logger.exception("Failed to patch fields")
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/sessions/{session_id}/word-counts")
async def patch_word_counts(session_id: str, request: PatchWordCountsRequest):
    """Persist per-session word count target overrides to the checkpoint.

    Called by the frontend when the user edits a section's target word count.
    The overrides are merged into word_count_targets in the LangGraph state
    so generate_element_node uses the user's preferred targets.
    """
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        config = session_manager._config_for(session_id)
        current_state = await session_manager._graph.aget_state(config)
        existing = (current_state.values or {}).get("word_count_targets") or {}
        merged = {**existing, **request.targets}
        await session_manager._graph.aupdate_state(config, {"word_count_targets": merged})
        logger.info("Updated word count targets for %s: %s", session_id, list(request.targets.keys()))
        return {"status": "ok", "targets_updated": list(request.targets.keys())}
    except Exception as e:
        logger.exception("Failed to patch word counts")
        raise HTTPException(status_code=500, detail=str(e))


# --- Message endpoints ---


@app.post("/sessions/{session_id}/message", response_model=SendMessageResponse)
async def send_message(session_id: str, request: SendMessageRequest):
    """Send a user message and receive the agent's response."""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        result = await session_manager.send_message(
            session_id, request.content, field_overrides=request.field_overrides,
        )

        # Build agent messages from result
        agent_messages = []
        for content in result.get("messages", []):
            agent_messages.append(
                AgentMessage(role="agent", content=content)
            )

        # If there's an interrupt (next prompt), add it as a message
        interrupt = result.get("interrupt")
        if interrupt and isinstance(interrupt, str):
            agent_messages.append(
                AgentMessage(role="agent", content=interrupt)
            )
        elif interrupt and isinstance(interrupt, dict):
            agent_messages.append(
                AgentMessage(
                    role="agent",
                    content=interrupt.get("message", ""),
                    phase=interrupt.get("phase"),
                    current_field=interrupt.get("current_field"),
                    missing_fields=interrupt.get("missing_fields"),
                )
            )

        state = result.get("state", {})
        return SendMessageResponse(
            messages=agent_messages,
            phase=state.get("phase", "unknown"),
            session_state=SessionState(**state),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to process message")
        raise HTTPException(status_code=500, detail=str(e))


# --- Draft endpoints ---


@app.get("/sessions/{session_id}/draft", response_model=DraftState)
async def get_draft(session_id: str):
    """Get draft state including all elements."""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        elements = await session_manager.get_draft_elements(session_id)
        state = await session_manager.get_session_state(session_id)
        return DraftState(
            session_id=session_id,
            phase=state.get("phase", "unknown"),
            elements=[DraftElementSummary(**e) for e in elements],
        )
    except Exception as e:
        logger.exception("Failed to get draft")
        raise HTTPException(status_code=500, detail=str(e))


# --- Export endpoints ---


@app.get("/sessions/{session_id}/export")
async def export_document(session_id: str, format: str = "markdown"):
    """Export the draft document in the specified format.

    Query params:
        format: "markdown" or "word" (default: "markdown")
    """
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    if format not in ("markdown", "word"):
        raise HTTPException(status_code=400, detail="Format must be 'markdown' or 'word'")
    try:
        file_bytes, content_type = await session_manager.get_export_bytes(
            session_id, format=format
        )
        ext = ".md" if format == "markdown" else ".docx"
        return Response(
            content=file_bytes,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="position_description{ext}"'
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to export document")
        raise HTTPException(status_code=500, detail=str(e))


# --- LLM Configuration ---


@app.get("/config", response_model=LLMConfigResponse)
async def get_config():
    """Check whether an API key is configured and return the current base URL."""
    return LLMConfigResponse(
        has_key=bool(os.environ.get("OPENAI_API_KEY")),
        base_url=os.environ.get("OPENAI_BASE_URL"),
    )


@app.get("/config/word-counts")
async def get_word_count_defaults():
    """Return default word count targets from the backend config.

    Single source of truth — frontend fetches these instead of hardcoding.
    """
    return TARGET_WORD_COUNTS


@app.post("/config", response_model=LLMConfigResponse)
async def set_config(request: LLMConfigRequest):
    """Set the OpenAI API key and optional custom endpoint at runtime."""
    os.environ["OPENAI_API_KEY"] = request.api_key
    if request.base_url:
        os.environ["OPENAI_BASE_URL"] = request.base_url
    elif "OPENAI_BASE_URL" in os.environ:
        del os.environ["OPENAI_BASE_URL"]
    logger.info("LLM configuration updated (key set, base_url=%s)", request.base_url or "default")
    return LLMConfigResponse(
        has_key=True,
        base_url=request.base_url,
    )


# --- WebSocket ---


@app.websocket("/sessions/{session_id}/stream")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for streaming chat."""
    await websocket_chat(websocket, session_id, session_manager)


# --- Health ---


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "pd3r"}
