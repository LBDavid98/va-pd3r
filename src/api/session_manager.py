"""Session manager for PD3r API.

Manages graph instances, checkpointing, and the interrupt/resume pattern
for API-driven conversations (replacing the CLI chat loop in main.py).
"""

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.graphs.main_graph import build_graph
from src.models.draft import DraftElement, create_all_draft_elements
from src.config.intake_fields import INTAKE_FIELDS

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages PD3r agent sessions.

    Each session has a unique thread_id and maintains state via
    LangGraph's checkpointer. The interrupt/resume pattern maps to:
    - Create session → run graph until first interrupt
    - Send message → resume graph with user input, run until next interrupt
    """

    def __init__(self):
        self._checkpointer = MemorySaver()
        self._builder = build_graph()
        self._graph = self._builder.compile(checkpointer=self._checkpointer)
        # Track active sessions and their metadata
        self._sessions: dict[str, dict[str, Any]] = {}
        # Track in-flight graph tasks for cancellation
        self._active_tasks: dict[str, asyncio.Task] = {}

    async def create_session(self) -> tuple[str, dict]:
        """Create a new session and run until first interrupt.

        Returns:
            (session_id, initial_response) where initial_response contains
            the agent's greeting and initial state.
        """
        session_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": session_id}}

        self._sessions[session_id] = {
            "thread_id": session_id,
            "position_title": None,
        }

        # Run graph until first interrupt (agent greeting)
        result = None
        async for event in self._graph.astream({}, config, stream_mode="values"):
            result = event

        # Get interrupt value (the agent's prompt)
        interrupt_data = await self._get_interrupt(config)

        return session_id, {
            "state": self._extract_state(session_id, result),
            "interrupt": interrupt_data,
        }

    async def create_seeded_session(self, script_id: str, phase: str) -> tuple[str, dict]:
        """Create a session pre-populated at a specific phase from captured fixtures.

        Args:
            script_id: Test script ID (e.g. 'program-analyst', 'supervisory')
            phase: Target phase to seed at (e.g. 'interview', 'requirements', 'drafting', 'complete')

        Returns:
            (session_id, initial_response) with state at the target phase.
        """
        # Load fixture
        fixture_path = Path(__file__).parent.parent.parent / "output" / "test_fixtures" / f"{script_id}_states.json"
        if not fixture_path.exists():
            raise ValueError(f"No fixture found for script '{script_id}' at {fixture_path}")

        with open(fixture_path) as f:
            fixtures = json.load(f)

        if phase not in fixtures:
            available = list(fixtures.keys())
            raise ValueError(f"Phase '{phase}' not in fixture. Available: {available}")

        snap = fixtures[phase]

        # Create a normal session first (establishes checkpoint)
        session_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": session_id}}

        self._sessions[session_id] = {
            "thread_id": session_id,
            "position_title": snap.get("interview_values", {}).get("position_title"),
        }

        # Run graph to establish checkpoint (runs init_node → interrupt)
        result = None
        async for event in self._graph.astream({}, config, stream_mode="values"):
            result = event

        # Build interview_data dict from fixture values
        interview_values = snap.get("interview_values", {})
        interview_data: dict[str, dict] = {}
        for field_name, value in interview_values.items():
            interview_data[field_name] = {
                "value": value,
                "raw_input": None,
                "needs_confirmation": False,
                "confirmed": True,
            }

        # Determine supervisory status
        is_supervisor = bool(interview_values.get("is_supervisor"))

        # Build state update
        state_update: dict[str, Any] = {
            "phase": phase,
            "interview_data": interview_data,
            "missing_fields": snap.get("missing_fields", []),
            "current_field": snap.get("current_field"),
        }

        # For drafting/complete phases, create draft elements
        if phase in ("drafting", "review", "complete"):
            fixture_elements = snap.get("draft_elements", [])
            # Create full DraftElement objects, overlay fixture content/status
            draft_models = create_all_draft_elements(is_supervisor)
            draft_dicts = []
            fixture_by_name = {e["name"]: e for e in fixture_elements if e.get("name")}
            for model in draft_models:
                d = model.model_dump()
                overlay = fixture_by_name.get(model.name)
                if overlay:
                    if overlay.get("status"):
                        d["status"] = overlay["status"]
                    if overlay.get("content"):
                        # Fixture truncates content — use it anyway for seeding
                        d["content"] = overlay["content"]
                draft_dicts.append(d)

            state_update["draft_elements"] = draft_dicts
            state_update["current_element_index"] = 0
            state_update["current_element_name"] = draft_dicts[0]["name"] if draft_dicts else None

        # Inject state into checkpoint
        await self._graph.aupdate_state(config, state_update)

        # Build greeting message for the seeded phase
        greetings = {
            "init": "Welcome! I'm Pete, your Position Description writer.",
            "interview": f"Resuming interview for {interview_values.get('position_title', 'this position')}.",
            "requirements": "Here's a summary of the information collected. Please review and confirm.",
            "drafting": f"Drafting started for {interview_values.get('position_title', 'this position')}. Review each section as it's generated.",
            "review": "All sections drafted. Review the complete document and request any changes.",
            "complete": "The position description is complete. You can export it or write another.",
        }

        return session_id, {
            "state": self._extract_state(session_id, {**state_update, "messages": []}),
            "interrupt": greetings.get(phase, "Session created"),
        }

    async def send_message(
        self, session_id: str, content: str, field_overrides: dict[str, Any] | None = None,
    ) -> dict:
        """Send a user message and get the agent's response.

        Args:
            session_id: The session ID
            content: User message text
            field_overrides: Optional dict of field_name → new_value to patch
                into interview_data before the graph resumes.

        Returns:
            Response dict with agent messages, state, and interrupt data

        Raises:
            asyncio.CancelledError: If the task was cancelled via stop_session()
        """
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")

        # Register the current task for cancellation support
        task = asyncio.current_task()
        if task:
            self._active_tasks[session_id] = task

        try:
            config = self._config_for(session_id)

            # Apply field overrides before resuming the graph
            if field_overrides:
                await self._apply_field_overrides(config, field_overrides)

            # Snapshot message count before this turn so we only return NEW messages
            pre_state = await self._graph.aget_state(config)
            pre_msg_count = len(pre_state.values.get("messages", [])) if pre_state and pre_state.values else 0

            # Resume graph with user input
            result = None
            async for event in self._graph.astream(
                Command(resume=content), config, stream_mode="values"
            ):
                result = event

            # Collect only NEW AI messages from this turn
            messages = []
            if result and "messages" in result:
                for msg in result["messages"][pre_msg_count:]:
                    if hasattr(msg, "type") and msg.type == "ai":
                        messages.append(msg.content)

            # Track position title
            if result and "interview_data" in result:
                interview_data = result.get("interview_data", {})
                title = interview_data.get("position_title", {}).get("value")
                if title:
                    self._sessions[session_id]["position_title"] = title

            # Get interrupt value
            interrupt_data = await self._get_interrupt(config)

            return {
                "messages": messages,
                "state": self._extract_state(session_id, result),
                "interrupt": interrupt_data,
            }
        finally:
            self._active_tasks.pop(session_id, None)

    async def stop_session(self, session_id: str) -> bool:
        """Cancel the active task for a session if one is running.

        Returns:
            True if a task was cancelled, False if session was idle.
        """
        task = self._active_tasks.get(session_id)
        if task and not task.done():
            task.cancel()
            logger.info("Cancelled active task for session %s", session_id)
            return True
        return False

    async def restart_session(self, session_id: str) -> tuple[str, dict]:
        """Stop any active task and restart the session with a new thread.

        Returns:
            (session_id, initial_response) — same shape as create_session()
        """
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")

        # Cancel any running work
        await self.stop_session(session_id)

        # Generate a fresh thread_id so the graph starts clean
        new_thread_id = str(uuid.uuid4())
        self._sessions[session_id]["thread_id"] = new_thread_id
        self._sessions[session_id]["position_title"] = None

        config = {"configurable": {"thread_id": new_thread_id}}

        # Run graph until first interrupt (agent greeting)
        result = None
        async for event in self._graph.astream({}, config, stream_mode="values"):
            result = event

        interrupt_data = await self._get_interrupt(config)

        return session_id, {
            "state": self._extract_state(session_id, result),
            "interrupt": interrupt_data,
        }

    async def get_session_state(self, session_id: str) -> dict:
        """Get current session state."""
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")

        config = self._config_for(session_id)
        state = await self._graph.aget_state(config)

        if state and state.values:
            return self._extract_state(session_id, state.values)

        return self._extract_state(session_id, {})

    async def get_draft_elements(self, session_id: str) -> list[dict]:
        """Get draft elements for a session."""
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")

        config = self._config_for(session_id)
        state = await self._graph.aget_state(config)

        if not state or not state.values:
            return []

        draft_elements = state.values.get("draft_elements", [])
        interview_data = state.values.get("interview_data", {})

        # Exclude supervisory sections if position is not supervisory
        from src.models.draft import SUPERVISORY_DRAFT_ELEMENT_NAMES
        is_sup = self._is_supervisor(interview_data)

        elements = []
        for elem_dict in draft_elements:
            try:
                elem = DraftElement.model_validate(elem_dict)
                if not is_sup and elem.name in SUPERVISORY_DRAFT_ELEMENT_NAMES:
                    continue
                locked = elem_dict.get("_locked", False)
                # Build QA summary if available
                qa_summary = None
                if elem.qa_review is not None:
                    qa_summary = {
                        "passes": elem.qa_review.passes,
                        "overall_feedback": elem.qa_review.overall_feedback,
                        "checks": [
                            {
                                "requirement_id": c.requirement_id,
                                "passed": c.passed,
                                "explanation": c.explanation,
                                "severity": c.severity,
                                "suggestion": c.suggestion,
                            }
                            for c in elem.qa_review.check_results
                        ],
                        "passed_count": elem.qa_review.passed_count,
                        "failed_count": elem.qa_review.failed_count,
                    }
                elements.append({
                    "name": elem.name,
                    "display_name": elem.display_name,
                    "status": elem.status,
                    "content": elem.content,
                    "locked": locked,
                    "qa_review": qa_summary,
                })
            except Exception as e:
                logger.warning(f"Failed to validate draft element: {e}")
                continue

        return elements

    async def get_export_bytes(self, session_id: str, format: str = "markdown") -> tuple[bytes, str]:
        """Export the draft as bytes.

        Args:
            session_id: Session ID
            format: "markdown" or "word"

        Returns:
            (file_bytes, content_type)
        """
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")

        config = self._config_for(session_id)
        state = await self._graph.aget_state(config)

        if not state or not state.values:
            raise ValueError("No draft data available for export")

        draft_elements = state.values.get("draft_elements", [])
        interview_data = state.values.get("interview_data", {})

        # Exclude supervisory sections if position is not supervisory
        from src.models.draft import SUPERVISORY_DRAFT_ELEMENT_NAMES
        is_sup = self._is_supervisor(interview_data)
        if not is_sup:
            draft_elements = [
                e for e in draft_elements
                if e.get("name") not in SUPERVISORY_DRAFT_ELEMENT_NAMES
            ]

        if format == "word":
            from src.tools.export_tools import export_to_word_bytes
            file_bytes = export_to_word_bytes(draft_elements, interview_data)
            return file_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            from src.tools.export_tools import export_to_markdown_bytes
            file_bytes = export_to_markdown_bytes(draft_elements, interview_data)
            return file_bytes, "text/markdown"

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def session_exists(self, session_id: str) -> bool:
        return session_id in self._sessions

    @staticmethod
    def _is_supervisor(interview_data: dict) -> bool:
        """Check is_supervisor from interview_data dict."""
        is_sup = interview_data.get("is_supervisor", {})
        if isinstance(is_sup, dict):
            return bool(is_sup.get("value"))
        return bool(is_sup)

    def _config_for(self, session_id: str) -> dict:
        """Return the LangGraph config for a session, using its current thread_id."""
        thread_id = self._sessions[session_id].get("thread_id", session_id)
        return {"configurable": {"thread_id": thread_id}}

    async def _get_interrupt(self, config: dict) -> dict | None:
        """Get interrupt data from the current graph state."""
        state = await self._graph.aget_state(config)
        if state and state.tasks:
            for task in state.tasks:
                if hasattr(task, "interrupts") and task.interrupts:
                    return task.interrupts[0].value
        return None

    async def _apply_field_overrides(self, config: dict, overrides: dict[str, Any]) -> None:
        """Patch interview_data in the checkpoint with caller-supplied values.

        Each override sets value, clears needs_confirmation, and sets confirmed=True.
        """
        state = await self._graph.aget_state(config)
        if not state or not state.values:
            return

        interview_data = dict(state.values.get("interview_data", {}))
        for field_name, new_value in overrides.items():
            existing = interview_data.get(field_name, {})
            if isinstance(existing, dict):
                existing = dict(existing)
            else:
                existing = {}
            existing["value"] = new_value
            existing["needs_confirmation"] = False
            existing["confirmed"] = True
            interview_data[field_name] = existing

        await self._graph.aupdate_state(config, {"interview_data": interview_data})
        logger.info("Applied field overrides: %s", list(overrides.keys()))

    def _extract_state(self, session_id: str, result: dict | None) -> dict:
        """Extract a clean state summary from graph state."""
        if not result:
            return {
                "session_id": session_id,
                "phase": "init",
                "position_title": None,
                "collected_fields": [],
                "current_field": None,
                "missing_fields": [],
                "fields_needing_confirmation": [],
                "interview_data_values": {},
                "is_supervisor": None,
                "draft_element_count": 0,
                "current_element_name": None,
                "should_end": False,
            }

        # Extract collected fields and values from interview_data
        interview_data = result.get("interview_data", {})
        collected = []
        interview_data_values: dict[str, Any] = {}
        is_supervisor: bool | None = None

        for field_name, element in interview_data.items():
            if isinstance(element, dict) and element.get("value") is not None:
                collected.append(field_name)
                interview_data_values[field_name] = element["value"]
                if field_name == "is_supervisor":
                    interview_data_values[field_name] = element["value"]
                    is_supervisor = bool(element["value"])

        # Extract FES evaluation summary (lightweight — no does statements)
        fes_summary = None
        fes_raw = result.get("fes_evaluation")
        if isinstance(fes_raw, dict):
            factors = []
            for key in [
                "factor_1_knowledge", "factor_2_supervisory_controls",
                "factor_3_guidelines", "factor_4_complexity",
                "factor_5_scope_and_effect", "factor_6_personal_contacts",
                "factor_7_purpose_of_contacts", "factor_8_physical_demands",
                "factor_9_work_environment",
            ]:
                f = fes_raw.get(key)
                if isinstance(f, dict):
                    factors.append({
                        "factor_num": f.get("factor_num"),
                        "factor_name": f.get("factor_name", ""),
                        "level_code": f.get("level_code", ""),
                        "points": f.get("points", 0),
                    })
            fes_summary = {
                "grade": fes_raw.get("grade", ""),
                "total_points": fes_raw.get("total_points", 0),
                "factors": factors,
            }

        return {
            "session_id": session_id,
            "phase": result.get("phase", "init"),
            "position_title": self._sessions.get(session_id, {}).get("position_title"),
            "collected_fields": collected,
            "current_field": result.get("current_field"),
            "missing_fields": result.get("missing_fields", []),
            "fields_needing_confirmation": result.get("fields_needing_confirmation", []),
            "interview_data_values": interview_data_values,
            "is_supervisor": is_supervisor,
            "draft_element_count": len(result.get("draft_elements", [])),
            "current_element_name": result.get("current_element_name"),
            "should_end": result.get("should_end", False),
            "fes_evaluation": fes_summary,
        }
