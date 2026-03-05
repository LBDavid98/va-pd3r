"""Unit tests for init node."""

import pytest

from src.constants import REQUIRED_FIELDS
from src.nodes.init_node import GREETING, RESTART_GREETING, init_node


class TestInitNode:
    """Tests for init_node."""

    def test_returns_greeting(self):
        """Init node returns the greeting message."""
        state = {}

        result = init_node(state)

        assert result["next_prompt"] == GREETING
        assert len(result["messages"]) == 1
        assert result["messages"][0].content == GREETING

    def test_sets_init_phase(self):
        """Init node sets phase to init."""
        state = {}

        result = init_node(state)

        assert result["phase"] == "init"

    def test_initializes_interview_data(self):
        """Init node creates empty interview data."""
        state = {}

        result = init_node(state)

        assert result["interview_data"] is not None
        assert isinstance(result["interview_data"], dict)

    def test_sets_missing_fields(self):
        """Init node sets missing_fields to required fields."""
        state = {}

        result = init_node(state)

        assert result["missing_fields"] == list(REQUIRED_FIELDS)

    def test_initializes_draft_state(self):
        """Init node initializes drafting state."""
        state = {}

        result = init_node(state)

        assert result["draft_elements"] == []
        assert result["current_element_index"] == 0

    def test_sets_control_flags(self):
        """Init node sets control flags correctly."""
        state = {}

        result = init_node(state)

        assert result["should_end"] is False
        assert result["fields_needing_confirmation"] == []
        assert result["current_field"] is None
        assert result["last_intent"] is None
        assert result["pending_question"] is None
        assert result["draft_requirements"] is None


class TestInitNodeResume:
    """Tests for resume flow in init_node."""
    
    def test_resume_with_position_title(self):
        """Resume shows title-specific greeting."""
        state = {
            "is_resume": True,
            "phase": "interview",
            "interview_data": {
                "position_title": {"value": "IT Specialist", "confirmed": True},
            },
        }
        
        result = init_node(state)
        
        assert "Welcome back" in result["next_prompt"]
        assert "IT Specialist" in result["next_prompt"]
        assert "interview" in result["next_prompt"]
        assert result["is_resume"] is False  # Flag cleared
    
    def test_resume_without_position_title(self):
        """Resume shows generic greeting when no title."""
        state = {
            "is_resume": True,
            "phase": "init",
            "interview_data": {},
        }
        
        result = init_node(state)
        
        assert "Welcome back" in result["next_prompt"]
        assert "session in progress" in result["next_prompt"]
        assert result["is_resume"] is False
    
    def test_resume_preserves_state(self):
        """Resume does not reset existing state."""
        state = {
            "is_resume": True,
            "phase": "drafting",
            "interview_data": {
                "position_title": {"value": "Manager", "confirmed": True},
            },
            "draft_elements": [{"name": "introduction"}],
            "current_element_index": 1,
        }
        
        result = init_node(state)
        
        # Should not include state-resetting keys
        assert "interview_data" not in result
        assert "draft_elements" not in result
        assert "phase" not in result
    
    def test_restart_uses_restart_greeting(self):
        """Restart uses different greeting than new session."""
        state = {"is_restart": True}
        
        result = init_node(state)
        
        assert result["next_prompt"] == RESTART_GREETING
        assert result["is_restart"] is False
    
    def test_new_session_uses_standard_greeting(self):
        """New session uses standard greeting."""
        state = {"is_restart": False, "is_resume": False}
        
        result = init_node(state)
        
        assert result["next_prompt"] == GREETING
