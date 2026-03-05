"""Integration tests for Phase 1 Foundation."""

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.graphs.main_graph import compile_graph


def get_initial_state():
    """Return a valid initial state for the graph."""
    return {
        "messages": [],
        "phase": "init",
        "interview_data": None,
        "current_field": None,
        "missing_fields": [],
        "fields_needing_confirmation": [],
        "last_intent": None,
        "pending_question": None,
        "draft_requirements": None,
        "draft_elements": [],
        "current_element_index": 0,
        "should_end": False,
        "next_prompt": "",
    }


class TestFoundationIntegration:
    """Integration tests for basic conversation loop."""

    @pytest.fixture
    def graph(self):
        """Create a fresh graph with checkpointer for each test."""
        checkpointer = MemorySaver()
        return compile_graph(checkpointer=checkpointer)

    @pytest.fixture
    def config(self):
        """Thread config for graph invocation."""
        return {"configurable": {"thread_id": "test-thread-1"}}

    def test_can_greet_user(self, graph, config):
        """Test: init node produces greeting message."""
        # Invoke graph - will hit interrupt at user_input
        result = graph.invoke(get_initial_state(), config=config)

        # Check that we got an interrupt (the graph paused for user input)
        # The state should have the greeting in messages
        state = graph.get_state(config)

        assert state.values.get("phase") == "init"
        assert len(state.values.get("messages", [])) >= 1

        # Check greeting content
        first_message = state.values["messages"][0]
        assert "Pete" in first_message.content
        assert "Position Description" in first_message.content or "PD" in first_message.content

    def test_can_handle_yes_confirmation(self, graph, config):
        """Test: "yes" response routes to start_interview."""
        # First invocation - gets greeting, pauses at user_input
        graph.invoke(get_initial_state(), config=config)

        # Resume with "yes"
        graph.invoke(Command(resume="yes"), config=config)

        # Check state after processing "yes"
        state = graph.get_state(config)

        # Should have classified intent as "confirm"
        assert state.values.get("last_intent") == "confirm"

        # Should have at least 2 messages (greeting + user response)
        assert len(state.values.get("messages", [])) >= 2

    @pytest.mark.llm
    def test_can_handle_no_rejection(self, graph, config, skip_without_api_key):
        """Test: "no" response ends conversation gracefully.
        
        Requires LLM: Invokes intent_classification_node.
        """
        # First invocation - gets greeting, pauses at user_input
        graph.invoke(get_initial_state(), config=config)

        # Resume with "no" - this rejects the help offer
        result = graph.invoke(Command(resume="no"), config=config)

        # Check state after processing "no"
        state = graph.get_state(config)

        # Should have classified intent as "reject"
        assert state.values.get("last_intent") == "reject"

        # In init phase, reject goes to end_conversation which asks "write another?"
        # So we need to also respond to that - graph should be waiting at user_input
        assert state.values.get("phase") == "complete"
        assert "write another" in state.values.get("next_prompt", "").lower()

        # Now respond "no" to "write another?" prompt
        graph.invoke(Command(resume="no"), config=config)
        state = graph.get_state(config)

        # Now should_end should be True
        assert state.values.get("should_end") is True
        assert state.values.get("wants_another") is False

    @pytest.mark.llm
    def test_can_handle_quit_command(self, graph, config, skip_without_api_key):
        """Test: "quit" command ends conversation from any point.
        
        Requires LLM: Invokes intent_classification_node.
        """
        # First invocation
        graph.invoke(get_initial_state(), config=config)

        # Resume with "quit"
        graph.invoke(Command(resume="quit"), config=config)

        state = graph.get_state(config)

        assert state.values.get("last_intent") == "quit"
        # end_conversation now asks "write another?" before truly ending
        assert state.values.get("phase") == "complete"
        assert "write another" in state.values.get("next_prompt", "").lower()

        # Respond "no" to "write another?"
        graph.invoke(Command(resume="no"), config=config)
        state = graph.get_state(config)

        assert state.values.get("should_end") is True
        assert state.values.get("wants_another") is False

    def test_checkpointer_saves_state(self, graph, config):
        """Test: State is persisted across invocations."""
        # First invocation
        graph.invoke(get_initial_state(), config=config)

        # Get state snapshot
        state1 = graph.get_state(config)
        messages_count_1 = len(state1.values.get("messages", []))

        # Resume with response
        graph.invoke(Command(resume="yes"), config=config)

        # Get new state
        state2 = graph.get_state(config)
        messages_count_2 = len(state2.values.get("messages", []))

        # Messages should have accumulated
        assert messages_count_2 > messages_count_1

        # State history should be available
        history = list(graph.get_state_history(config))
        assert len(history) >= 2

    def test_restart_command_resets_state(self, graph, config):
        """Test: "restart" command reinitializes the conversation."""
        # First invocation
        graph.invoke(get_initial_state(), config=config)

        # Say yes to start
        graph.invoke(Command(resume="yes"), config=config)

        state_before = graph.get_state(config)
        assert state_before.values.get("last_intent") == "confirm"

        # Request restart
        graph.invoke(Command(resume="restart"), config=config)

        state_after = graph.get_state(config)

        # Should have reset to init phase (init_node resets all state including last_intent)
        assert state_after.values.get("phase") == "init"
        # After restart, we're in fresh state, so last_intent is reset to None
        assert state_after.values.get("last_intent") is None
        # But we should have the greeting message again
        assert len(state_after.values.get("messages", [])) >= 1


class TestMessageFlow:
    """Tests for message accumulation and flow."""

    @pytest.fixture
    def graph(self):
        """Create a fresh graph with checkpointer."""
        return compile_graph(checkpointer=MemorySaver())

    @pytest.fixture
    def config(self):
        """Thread config."""
        return {"configurable": {"thread_id": "test-thread-2"}}

    def test_messages_accumulate_correctly(self, graph, config):
        """Test: Messages from user and agent accumulate in order."""
        from langchain_core.messages import AIMessage, HumanMessage

        # Start conversation
        graph.invoke(get_initial_state(), config=config)
        state1 = graph.get_state(config)

        # First message should be AI greeting
        assert len(state1.values["messages"]) >= 1
        assert isinstance(state1.values["messages"][0], AIMessage)

        # User responds
        graph.invoke(Command(resume="I need help with a PD"), config=config)
        state2 = graph.get_state(config)

        # Should now have AI greeting + Human response
        messages = state2.values["messages"]
        assert len(messages) >= 2

        # Find the human message
        human_messages = [m for m in messages if isinstance(m, HumanMessage)]
        assert len(human_messages) >= 1
        assert "PD" in human_messages[-1].content


class TestRewriteContext:
    """Tests for rewrite context and model escalation."""

    def test_draft_element_rewrite_context_structure(self):
        """Test: Rewrite context includes all required fields."""
        from src.models.draft import DraftAttempt, DraftElement, QACheckResult, QAReview

        # Create element with failed QA attempt
        element = DraftElement(
            name="major_duties",
            display_name="Major Duties",
            order=1,
            content="Second attempt content",
            status="drafted",
            qa_review=QAReview(
                passes=False,
                check_results=[
                    QACheckResult(
                        requirement_id="req_1",
                        passed=False,
                        explanation="Missing supervisory statement",
                        severity="critical",
                    )
                ],
                overall_feedback="Needs supervisory duties",
            ),
            draft_history=[
                DraftAttempt(
                    content="First attempt - too brief",
                    qa_passed=False,
                    qa_feedback="Missing key details",
                    qa_failures=["Missing supervisory duties", "Grade unclear"],
                    rewrite_reason="qa_failure",
                )
            ],
            rewrite_reason="qa_failure",
        )

        context = element.get_rewrite_context()

        # Verify structure
        assert context["attempt_number"] == 2
        assert len(context["previous_drafts"]) == 1
        assert context["rewrite_reason"] == "qa_failure"
        assert len(context["failure_reasons"]) >= 2
        assert "[QA]" in context["failure_reasons"][0]

    def test_rewrite_template_can_render(self):
        """Test: Rewrite template renders with context."""
        from jinja2 import Environment, PackageLoader

        jinja_env = Environment(
            loader=PackageLoader("src.prompts", "templates"),
            trim_blocks=True,
            lstrip_blocks=True,
        )

        template = jinja_env.get_template("draft_rewrite.jinja")

        # Minimal context for rendering (matching template expectations)
        context = {
            "section_name": "Major Duties",
            "section_description": "Overview of primary duties",
            "attempt_number": 2,
            "previous_drafts": [
                {
                    "content": "First attempt content",
                    "qa_passed": False,
                    "qa_feedback": "Too brief",
                    "qa_failures": ["Missing supervisory statement"],
                }
            ],
            "failure_reasons": ["[QA] Missing supervisory statement"],
            "has_user_feedback": False,
            "latest_user_feedback": None,
            "rewrite_reason": "qa_failure",
            # Position context fields
            "position_title": "Test Position",
            "series": "2210",
            "grade": "13",
            "organization": "Test Org",
            "reports_to": "Test Supervisor",
            "is_supervisor": False,
        }

        prompt = template.render(**context)

        # Verify template renders key content
        assert "Major Duties" in prompt
        assert "REWRITE ATTEMPT 2" in prompt
        assert "Missing supervisory statement" in prompt

    def test_model_escalation_on_rewrite(self):
        """Test: Model escalation happens on rewrite attempts."""
        from unittest.mock import patch

        from src.utils import (
            DEFAULT_MODEL,
            DEFAULT_TEMPERATURE,
            REWRITE_MODEL,
            REWRITE_TEMPERATURE,
            get_model_for_attempt,
        )

        with patch("src.utils.llm.ChatOpenAI") as mock_chat:
            mock_chat.return_value.model_name = DEFAULT_MODEL
            # First attempt - default settings
            get_model_for_attempt(1)
            first_call = mock_chat.call_args.kwargs
            assert first_call["temperature"] == DEFAULT_TEMPERATURE

        with patch("src.utils.llm.ChatOpenAI") as mock_chat:
            mock_chat.return_value.model_name = REWRITE_MODEL
            # Second attempt - escalated settings
            get_model_for_attempt(2)
            second_call = mock_chat.call_args.kwargs
            assert second_call["temperature"] == REWRITE_TEMPERATURE
            assert second_call["model"] == REWRITE_MODEL
