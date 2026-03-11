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
        Client sends: {"type": "element_action", "data": {"element": "...", "action": "approve|reject|regenerate", "feedback": "..."}}
        Client sends: {"type": "stop"}
        Client sends: {"type": "ping"}
        Server sends: {"type": "agent_message", "data": {"content": "...", "phase": "...", "prompt": "..."}}
        Server sends: {"type": "state_update", "data": {...session state...}}
        Server sends: {"type": "element_update", "data": {"name": "...", "status": "...", ...}}
        Server sends: {"type": "activity_update", "data": {"activity": "drafting|reviewing|...", "element": "...", "detail": "..."}}
        Server sends: {"type": "done"}  — signals processing complete; client should stop typing indicator
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
            # Stream AI messages and state updates in real-time as nodes complete
            async def stream_message(msg_content: str):
                await websocket.send_json({
                    "type": "agent_message",
                    "data": {"content": msg_content},
                })

            async def stream_state(state_data: dict):
                await websocket.send_json({
                    "type": "state_update",
                    "data": state_data,
                })

            async def stream_element(element_data: dict):
                await websocket.send_json({
                    "type": "element_update",
                    "data": element_data,
                })

            async def stream_activity(activity_data: dict):
                await websocket.send_json({
                    "type": "activity_update",
                    "data": activity_data,
                })

            result = await manager.send_message(
                session_id, content, field_overrides=field_overrides,
                on_message=stream_message,
                on_state=stream_state,
                on_element_update=stream_element,
                on_activity=stream_activity,
            )

            # Send any remaining messages not already streamed
            for msg_content in result.get("messages", []):
                await websocket.send_json({
                    "type": "agent_message",
                    "data": {"content": msg_content},
                })

            # Send interrupt/prompt if present (skip empty prompts)
            interrupt = result.get("interrupt")
            if interrupt:
                prompt_content = interrupt if isinstance(interrupt, str) else interrupt.get("prompt", interrupt.get("message", ""))
                if not prompt_content:
                    logger.warning("Empty interrupt prompt for session %s, skipping", session_id)
                    interrupt = None
            if interrupt:
                prompt_data = {"content": prompt_content, "prompt": prompt_content}
                if isinstance(interrupt, dict):
                    prompt_data["phase"] = interrupt.get("phase")
                    prompt_data["current_field"] = interrupt.get("current_field")
                    prompt_data["missing_fields"] = interrupt.get("missing_fields")
                await websocket.send_json({
                    "type": "agent_message",
                    "data": prompt_data,
                })

            # Send final state update
            state = result.get("state", {})
            await websocket.send_json({
                "type": "state_update",
                "data": state,
            })

            # Signal processing complete — frontend uses this as the
            # single source of truth to turn off the typing indicator.
            await websocket.send_json({"type": "done"})

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

            if msg_type == "element_action":
                # Structured element action — bypass LLM intent classification.
                # Translate to a structured content prefix that the graph can
                # short-circuit on, avoiding a wasted LLM call.
                ea_data = message.get("data", {})
                ea_element = ea_data.get("element", "")
                ea_action = ea_data.get("action", "")
                ea_feedback = ea_data.get("feedback", "")
                if not ea_element or ea_action not in ("approve", "reject", "regenerate"):
                    await websocket.send_json({
                        "type": "error",
                        "data": {"message": f"Invalid element_action: element={ea_element!r}, action={ea_action!r}"},
                    })
                    continue
                content = f"[ACTION:{ea_action}:{ea_element}]"
                if ea_feedback:
                    content += f" {ea_feedback}"
                field_overrides = None
                # Fall through to processing below (same as user_message)

            elif msg_type == "user_message":
                data = message.get("data", {})
                content = data.get("content", "")
                if not content:
                    await websocket.send_json({
                        "type": "error",
                        "data": {"message": "Empty message content"},
                    })
                    continue
                field_overrides = data.get("field_overrides") or None

            else:
                await websocket.send_json({
                    "type": "error",
                    "data": {"message": f"Unknown message type: {msg_type}"},
                })
                continue

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
                        else:
                            logger.warning(
                                "Dropped %r message for session %s — processing in progress",
                                inner_type, session_id,
                            )
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
