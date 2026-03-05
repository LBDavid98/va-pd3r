"""End-to-end integration tests for complete conversation flows.

These tests validate the full agent workflow using scripted inputs
to simulate realistic user interactions.
"""

import pytest
import asyncio
import uuid
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.graphs.main_graph import build_graph


class TestGraphStructure:
    """Tests for graph structure and compilation."""

    def test_graph_has_all_required_nodes(self):
        """Graph should include all expected nodes."""
        builder = build_graph()
        nodes = list(builder.nodes.keys())

        expected_nodes = [
            # Phase 1-2
            "init",
            "user_input",
            "classify_intent",
            "end_conversation",
            "map_answers",
            "answer_question",
            "prepare_next",
            "check_interview_complete",
            # Phase 3
            "evaluate_fes",
            "gather_requirements",
            "generate_element",
            "qa_review",
            "handle_draft_response",
            "advance_element",
            # Phase 4
            "finalize",
            "handle_element_revision",
            "handle_write_another",
            "export_document",
        ]

        for node in expected_nodes:
            assert node in nodes, f"Missing node: {node}"

    def test_graph_compiles_successfully(self):
        """Graph should compile with checkpointer."""
        builder = build_graph()
        checkpointer = MemorySaver()

        graph = builder.compile(checkpointer=checkpointer)

        assert graph is not None

    def test_graph_exports_mermaid(self):
        """Graph should export to mermaid format."""
        from src.graphs.export import get_mermaid_syntax

        builder = build_graph()
        graph = builder.compile(checkpointer=MemorySaver())

        mermaid = get_mermaid_syntax(graph)

        # Check key nodes are in output
        assert "init" in mermaid
        assert "user_input" in mermaid
        assert "classify_intent" in mermaid


class TestScriptedInputProvider:
    """Tests for the scripted input test helper."""

    def test_provides_field_answers(self):
        """Should provide answers for known fields."""
        from scripts.run_e2e_test import ScriptedInputProvider

        provider = ScriptedInputProvider(
            answers={"position_title": "Data Scientist"}
        )
        provider.set_current_field("position_title")

        response = provider.get_input("What is the position title?")

        assert response == "Data Scientist"

    def test_provides_confirmation_responses(self):
        """Should provide yes/no for confirmation prompts."""
        from scripts.run_e2e_test import ScriptedInputProvider

        provider = ScriptedInputProvider(
            answers={},
            default_confirmations={"write_another": "no"}
        )

        response = provider.get_input("Would you like to write another PD?")

        assert response == "no"

    def test_logs_inputs(self):
        """Should log all inputs provided."""
        from scripts.run_e2e_test import ScriptedInputProvider

        provider = ScriptedInputProvider(
            answers={"series": "2210"}
        )
        provider.set_current_field("series")
        provider.get_input("What series?")

        assert len(provider.input_log) == 1


class TestTestConfig:
    """Tests for the minimal test configuration."""

    def test_minimal_fields_defined(self):
        """Minimal config should have required fields."""
        from src.config.test_config import (
            MINIMAL_INTAKE_SEQUENCE,
            MINIMAL_INTAKE_FIELDS,
            TEST_ANSWERS,
        )

        # Check sequence has fields
        assert len(MINIMAL_INTAKE_SEQUENCE) >= 3

        # Check all sequence fields have definitions
        for field in MINIMAL_INTAKE_SEQUENCE:
            assert field in MINIMAL_INTAKE_FIELDS

        # Check all sequence fields have test answers
        for field in MINIMAL_INTAKE_SEQUENCE:
            assert field in TEST_ANSWERS

    def test_minimal_draft_elements(self):
        """Minimal config should have at least one draft element."""
        from src.config.test_config import MINIMAL_DRAFT_ELEMENT_NAMES

        assert len(MINIMAL_DRAFT_ELEMENT_NAMES) >= 1
        assert "introduction" in MINIMAL_DRAFT_ELEMENT_NAMES


@pytest.mark.asyncio
class TestBasicGraphExecution:
    """Basic tests for graph execution flow."""

    async def test_graph_starts_with_init(self):
        """Graph should start and reach init phase."""
        builder = build_graph()
        checkpointer = MemorySaver()
        graph = builder.compile(checkpointer=checkpointer)

        config = {"configurable": {"thread_id": str(uuid.uuid4())}}

        # Start graph with empty dict (required input)
        events = []
        async for event in graph.astream({}, config, stream_mode="values"):
            events.append(event)
            break  # Just get first event

        assert len(events) >= 1
        # First event should have init phase
        assert events[0].get("phase") in ["init", None]

    async def test_graph_produces_interrupt(self):
        """Graph should produce interrupt for user input."""
        builder = build_graph()
        checkpointer = MemorySaver()
        graph = builder.compile(checkpointer=checkpointer)

        config = {"configurable": {"thread_id": str(uuid.uuid4())}}

        # Run until interrupt (need to provide initial input)
        async for event in graph.astream({}, config, stream_mode="values"):
            pass

        # Check for interrupt
        state = await graph.aget_state(config)

        # Should have tasks with interrupt
        assert state.tasks is not None


@pytest.mark.asyncio
@pytest.mark.llm
class TestInterviewFlow:
    """Integration tests for the interview flow (requires LLM)."""

    async def test_completes_greeting(self, skip_without_api_key):
        """Agent should greet user and ask first question."""
        builder = build_graph()
        checkpointer = MemorySaver()
        graph = builder.compile(checkpointer=checkpointer)

        config = {"configurable": {"thread_id": str(uuid.uuid4())}}

        # Run until first interrupt (requires non-None input for LangGraph)
        result = None
        async for event in graph.astream({}, config, stream_mode="values"):
            result = event

        # Check state has interview phase
        state = await graph.aget_state(config)

        # Should be waiting for user input
        assert state.tasks is not None

        # Should have an interrupt with prompt
        interrupt_value = None
        for task in state.tasks:
            if hasattr(task, "interrupts") and task.interrupts:
                interrupt_value = task.interrupts[0].value
                break

        assert interrupt_value is not None
        assert "prompt" in interrupt_value

    async def test_processes_answer(self, skip_without_api_key):
        """Agent should process user answer and continue."""
        builder = build_graph()
        checkpointer = MemorySaver()
        graph = builder.compile(checkpointer=checkpointer)

        config = {"configurable": {"thread_id": str(uuid.uuid4())}}

        # Run until first interrupt (requires non-None input for LangGraph)
        async for event in graph.astream({}, config, stream_mode="values"):
            pass

        # Provide an answer
        input_cmd = Command(resume="IT Specialist for the Bureau of Economic Analysis")

        # Run next iteration
        result = None
        async for event in graph.astream(input_cmd, config, stream_mode="values"):
            result = event

        # Should have captured some data
        assert result is not None
        # Phase should still be early in flow
        assert result.get("phase") in ["init", "interview", "requirements"]


# =============================================================================
# TestE2EScripted removed - this was a full E2E integration test that belongs
# in scripts/run_e2e_test.py, not in the pytest suite. It was causing timeouts
# and hangs because it runs the full agent loop with real LLM calls.
#
# To run E2E tests, use:
#   poetry run python scripts/run_e2e_test.py --trace -v
# =============================================================================
