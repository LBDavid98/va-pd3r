"""Tests for write another flow nodes."""

import pytest

from src.nodes.handle_write_another_node import handle_write_another_node
from src.nodes.init_node import init_node, GREETING, RESTART_GREETING


class TestHandleWriteAnotherNode:
    """Tests for handle_write_another_node."""

    def test_confirm_intent_sets_wants_another_true(self):
        """When user confirms, wants_another should be True."""
        state = {"last_intent": "confirm", "phase": "complete"}

        result = handle_write_another_node(state)

        assert result["wants_another"] is True
        assert result["is_restart"] is True

    def test_reject_intent_sets_wants_another_false(self):
        """When user rejects, wants_another should be False."""
        state = {"last_intent": "reject", "phase": "complete"}

        result = handle_write_another_node(state)

        assert result["wants_another"] is False
        assert "is_restart" not in result

    def test_unknown_intent_asks_clarification(self):
        """When intent is unclear, should ask for clarification."""
        state = {"last_intent": "provide_information", "phase": "complete"}

        result = handle_write_another_node(state)

        assert "wants_another" not in result
        assert "next_prompt" in result
        assert "yes" in result["next_prompt"].lower()
        assert "no" in result["next_prompt"].lower()
        assert len(result["messages"]) == 1

    def test_empty_intent_asks_clarification(self):
        """When no intent, should ask for clarification."""
        state = {"phase": "complete"}

        result = handle_write_another_node(state)

        assert "wants_another" not in result
        assert "next_prompt" in result


class TestInitNodeRestart:
    """Tests for init_node restart functionality."""

    def test_fresh_start_uses_greeting(self):
        """Fresh conversation should use standard greeting."""
        state = {}

        result = init_node(state)

        assert result["next_prompt"] == GREETING
        assert result["messages"][0].content == GREETING
        assert result["phase"] == "init"
        assert result["wants_another"] is None
        assert result["is_restart"] is False

    def test_restart_uses_restart_greeting(self):
        """Restart should use restart greeting."""
        state = {"is_restart": True}

        result = init_node(state)

        assert result["next_prompt"] == RESTART_GREETING
        assert result["messages"][0].content == RESTART_GREETING
        assert result["phase"] == "init"
        # Flags should be reset
        assert result["wants_another"] is None
        assert result["is_restart"] is False

    def test_restart_resets_interview_data(self):
        """Restart should reset all interview and draft state."""
        state = {
            "is_restart": True,
            "interview_data": {"position_title": {"value": "Old Title"}},
            "draft_elements": [{"name": "introduction", "content": "Old content"}],
            "current_element_index": 5,
            "fes_evaluation": {"some": "data"},
        }

        result = init_node(state)

        # Should have fresh interview data
        assert result["interview_data"] is not None
        # Draft elements should be empty
        assert result["draft_elements"] == []
        # Current element index should be reset
        assert result["current_element_index"] == 0
        # FES evaluation should be cleared
        assert result["fes_evaluation"] is None

    def test_init_sets_current_element_name_to_none(self):
        """Init should reset current_element_name."""
        state = {"is_restart": True, "current_element_name": "major_duties"}

        result = init_node(state)

        assert result["current_element_name"] is None

    def test_is_restart_false_by_default(self):
        """When is_restart not in state, should use standard greeting."""
        state = {"is_restart": False}

        result = init_node(state)

        assert result["next_prompt"] == GREETING


class TestEndConversationNode:
    """Tests for end_conversation_node with write another prompt."""

    def test_first_call_asks_write_another(self):
        """First call should ask if user wants to write another."""
        from src.nodes.end_conversation_node import end_conversation_node, WRITE_ANOTHER_PROMPT
        
        state = {"wants_another": None, "phase": "review"}

        result = end_conversation_node(state)

        assert result["next_prompt"] == WRITE_ANOTHER_PROMPT
        assert result["phase"] == "complete"
        assert result["should_end"] is False
        assert len(result["messages"]) == 1

    def test_wants_another_false_sends_farewell(self):
        """When user said no, should send farewell."""
        from src.nodes.end_conversation_node import end_conversation_node, FAREWELL_MESSAGES

        state = {"wants_another": False, "phase": "complete"}

        result = end_conversation_node(state)

        assert result["should_end"] is True
        assert result["messages"][0].content == FAREWELL_MESSAGES[0]

    def test_wants_another_true_sets_restart_flag(self):
        """When user said yes, should set restart flag."""
        from src.nodes.end_conversation_node import end_conversation_node

        state = {"wants_another": True, "phase": "complete"}

        result = end_conversation_node(state)

        assert result.get("is_restart") is True
        assert result["should_end"] is False
