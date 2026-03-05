"""WebSocket endpoint for streaming PD3r chat.

Provides real-time bidirectional communication between the client and
the PD3r agent, streaming agent responses as they're produced.
"""

import asyncio
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from src.api.session_manager import SessionManager

logger = logging.getLogger(__name__)


async def websocket_chat(websocket: WebSocket, session_id: str, manager: SessionManager):
    """Handle a WebSocket chat connection for a session.

    Protocol:
        Client sends: {"type": "user_message", "data": {"content": "..."}}
        Client sends: {"type": "stop"}
        Client sends: {"type": "ping"}
        Server sends: {"type": "agent_message", "data": {"content": "...", "phase": "...", "prompt": "..."}}
        Server sends: {"type": "state_update", "data": {...session state...}}
        Server sends: {"type": "stopped", "data": {...session state...}}
        Server sends: {"type": "error", "data": {"message": "..."}}
        Server sends: {"type": "pong"}
    """
    await websocket.accept()

    if not manager.session_exists(session_id):
        await websocket.send_json({
            "type": "error",
            "data": {"message": f"Session {session_id} not found"},
        })
        await websocket.close(code=4004, reason="Session not found")
        return

    processing_task: asyncio.Task | None = None

    async def process_message(content: str, field_overrides: dict | None):
        """Run send_message and relay results back over the WebSocket."""
        try:
            result = await manager.send_message(
                session_id, content, field_overrides=field_overrides,
            )

            # Send agent messages
            for msg_content in result.get("messages", []):
                await websocket.send_json({
                    "type": "agent_message",
                    "data": {"content": msg_content},
                })

            # Send interrupt/prompt if present
            interrupt = result.get("interrupt")
            if interrupt:
                prompt_content = interrupt if isinstance(interrupt, str) else interrupt.get("message", "")
                prompt_data = {"content": prompt_content, "prompt": prompt_content}
                if isinstance(interrupt, dict):
                    prompt_data["phase"] = interrupt.get("phase")
                    prompt_data["current_field"] = interrupt.get("current_field")
                    prompt_data["missing_fields"] = interrupt.get("missing_fields")
                await websocket.send_json({
                    "type": "agent_message",
                    "data": prompt_data,
                })

            # Send state update
            state = result.get("state", {})
            await websocket.send_json({
                "type": "state_update",
                "data": state,
            })

        except asyncio.CancelledError:
            # Task was stopped by the user — send current state back
            logger.info("Processing cancelled for session %s", session_id)
            try:
                state = await manager.get_session_state(session_id)
                await websocket.send_json({
                    "type": "stopped",
                    "data": state,
                })
            except Exception:
                await websocket.send_json({
                    "type": "stopped",
                    "data": {},
                })
        except Exception as e:
            logger.exception("Error processing WebSocket message")
            await websocket.send_json({
                "type": "error",
                "data": {"message": str(e)},
            })

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "data": {"message": "Invalid JSON"},
                })
                continue

            msg_type = message.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if msg_type == "stop":
                if processing_task and not processing_task.done():
                    processing_task.cancel()
                    # Wait briefly for the cancellation to propagate
                    try:
                        await asyncio.wait_for(asyncio.shield(processing_task), timeout=2.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass
                else:
                    # Already idle — acknowledge anyway
                    await websocket.send_json({
                        "type": "stopped",
                        "data": {},
                    })
                continue

            if msg_type != "user_message":
                await websocket.send_json({
                    "type": "error",
                    "data": {"message": f"Unknown message type: {msg_type}"},
                })
                continue

            data = message.get("data", {})
            content = data.get("content", "")
            if not content:
                await websocket.send_json({
                    "type": "error",
                    "data": {"message": "Empty message content"},
                })
                continue

            field_overrides = data.get("field_overrides") or None

            # Cancel any prior task still running (shouldn't happen, but be safe)
            if processing_task and not processing_task.done():
                processing_task.cancel()
                try:
                    await processing_task
                except (asyncio.CancelledError, Exception):
                    pass

            # Run processing in a task so we can listen for stop in parallel
            processing_task = asyncio.create_task(
                process_message(content, field_overrides)
            )

            # Wait for either: processing to finish, or a new message from the client
            done = False
            while not done:
                receive_task = asyncio.create_task(websocket.receive_text())
                finished, _ = await asyncio.wait(
                    [processing_task, receive_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if processing_task in finished:
                    # Processing completed — cancel the pending receive and break
                    receive_task.cancel()
                    try:
                        await receive_task
                    except (asyncio.CancelledError, Exception):
                        pass
                    done = True
                elif receive_task in finished:
                    # Client sent something while processing — check if it's stop or ping
                    try:
                        raw_inner = receive_task.result()
                        inner_msg = json.loads(raw_inner)
                        inner_type = inner_msg.get("type", "")

                        if inner_type == "ping":
                            await websocket.send_json({"type": "pong"})
                        elif inner_type == "stop":
                            processing_task.cancel()
                            try:
                                await processing_task
                            except (asyncio.CancelledError, Exception):
                                pass
                            done = True
                        # Other messages while processing are dropped
                    except (json.JSONDecodeError, Exception):
                        pass

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.exception(f"WebSocket error for session {session_id}")
        try:
            await websocket.close(code=1011, reason=str(e))
        except Exception:
            pass
    finally:
        # Clean up any running task on disconnect
        if processing_task and not processing_task.done():
            processing_task.cancel()
            try:
                await processing_task
            except (asyncio.CancelledError, Exception):
                pass
