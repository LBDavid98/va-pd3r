"""Unit tests for graph nodes."""

import pytest

from src.nodes.end_conversation_node import end_conversation_node
from src.nodes.init_node import init_node
from src.nodes.intent_classification_node import intent_classification_node


def test_init_node_returns_state_updates(sample_state):
    """Test init node returns required state updates."""
    result = init_node(sample_state)

    assert "phase" in result
    assert "interview_data" in result
    assert "messages" in result
    assert result["phase"] == "init"


def test_end_conversation_node_asks_write_another(sample_state):
    """Test end conversation node asks about writing another PD."""
    result = end_conversation_node(sample_state)

    # With wants_another=None, should ask about writing another
    assert result["phase"] == "complete"
    assert result["should_end"] is False  # Not ending yet - asking question
    assert "write another" in result["next_prompt"].lower()
    assert len(result["messages"]) == 1


def test_end_conversation_node_sets_should_end_when_rejected(sample_state):
    """Test end conversation node sets should_end when user says no."""
    sample_state["wants_another"] = False

    result = end_conversation_node(sample_state)

    assert result["should_end"] is True
    assert result["phase"] == "complete"
    assert len(result["messages"]) == 1


async def test_intent_classification_node_with_quit(sample_state):
    """Test intent classification recognizes quit."""
    from langchain_core.messages import HumanMessage

    sample_state["messages"] = [HumanMessage(content="quit")]

    result = await intent_classification_node(sample_state)

    assert result["last_intent"] == "quit"


async def test_intent_classification_node_with_confirm(sample_state):
    """Test intent classification recognizes confirm."""
    from langchain_core.messages import HumanMessage

    sample_state["messages"] = [HumanMessage(content="yes")]

    result = await intent_classification_node(sample_state)

    assert result["last_intent"] == "confirm"
