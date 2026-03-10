"""Tests for error recovery across different nodes.

These tests verify that:
1. Nodes properly set last_error on failures
2. The error_handler node processes errors correctly
3. Recovery routing works end-to-end
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from langchain_core.messages import AIMessage

from src.models.state import AgentState
from src.nodes.error_handler_node import (
    error_handler_node,
    route_after_error,
    _extract_error_type,
    _get_user_message,
)


class TestErrorHandlerNode:
    """Tests for the error_handler_node function."""

    def test_clears_error_from_state(self):
        """Error handler clears last_error from state."""
        state: AgentState = {
            "last_error": "some_node: SomeError: Something went wrong",
        }
        result = error_handler_node(state)
        assert result.get("last_error") is None

    def test_returns_user_friendly_message(self):
        """Error handler returns user-friendly message."""
        state: AgentState = {
            "last_error": "export: LLMConnectionError: Connection failed",
        }
        result = error_handler_node(state)
        messages = result.get("messages", [])
        assert len(messages) == 1
        assert isinstance(messages[0], AIMessage)
        assert "trouble connecting" in messages[0].content.lower()

    def test_handles_missing_error_gracefully(self):
        """Error handler handles missing error gracefully."""
        state: AgentState = {}
        result = error_handler_node(state)
        # Should return empty dict without crashing
        assert result == {}

    def test_route_after_error_always_returns_user_input(self):
        """Route after error always goes to user_input."""
        state: AgentState = {}
        result = route_after_error(state)
        assert result == "user_input"


class TestExtractErrorType:
    """Tests for _extract_error_type helper."""

    def test_extracts_error_type_from_formatted_string(self):
        """Extracts error type from 'node: ErrorType: message' format."""
        error_str = "export_document: PermissionError: Cannot write file"
        result = _extract_error_type(error_str)
        assert result == "PermissionError"

    def test_handles_empty_string(self):
        """Returns empty string for empty input."""
        assert _extract_error_type("") == ""

    def test_handles_none(self):
        """Returns empty string for None input."""
        assert _extract_error_type(None) == ""

    def test_handles_malformed_string(self):
        """Returns empty string for malformed input."""
        assert _extract_error_type("no colons here") == ""


class TestGetUserMessage:
    """Tests for _get_user_message helper."""

    def test_returns_specific_message_for_known_error(self):
        """Returns specific message for known error type."""
        error_str = "node: LLMConnectionError: details"
        result = _get_user_message(error_str)
        assert "trouble connecting" in result.lower()

    def test_returns_default_for_unknown_error(self):
        """Returns default message for unknown error type."""
        error_str = "node: UnknownErrorType: details"
        result = _get_user_message(error_str)
        assert "unexpected issue" in result.lower()


class TestExportNodeErrorHandling:
    """Tests for error handling in export_document_node."""

    def test_permission_error_sets_last_error(self):
        """Permission error sets last_error for routing to error_handler."""
        from src.nodes.export_node import export_document_node
        
        state: AgentState = {
            "draft_elements": [{"name": "intro", "content": "test"}],
            "interview_data": {"position_title": {"value": "Test"}},
            "intent_classification": {"export_request": {"format": "word"}},
        }
        
        with patch("src.nodes.export_node.export_to_word") as mock_export:
            mock_export.side_effect = PermissionError("Cannot write to directory")
            result = export_document_node(state)
        
        assert "last_error" in result
        assert "PermissionError" in result["last_error"]
        assert "export_document" in result["last_error"]

    def test_os_error_sets_last_error(self):
        """OS error sets last_error for routing to error_handler."""
        from src.nodes.export_node import export_document_node
        
        state: AgentState = {
            "draft_elements": [{"name": "intro", "content": "test"}],
            "interview_data": {"position_title": {"value": "Test"}},
            "intent_classification": {"export_request": {"format": "markdown"}},
        }
        
        with patch("src.nodes.export_node.export_to_markdown") as mock_export:
            mock_export.side_effect = OSError("Disk full")
            result = export_document_node(state)
        
        assert "last_error" in result
        assert "OSError" in result["last_error"]

    def test_non_critical_error_allows_format_retry(self):
        """Non-critical error allows user to try different format."""
        from src.nodes.export_node import export_document_node
        
        state: AgentState = {
            "draft_elements": [{"name": "intro", "content": "test"}],
            "interview_data": {"position_title": {"value": "Test"}},
            "intent_classification": {"export_request": {"format": "word"}},
        }
        
        with patch("src.nodes.export_node.export_to_word") as mock_export:
            mock_export.side_effect = ValueError("Invalid content")
            result = export_document_node(state)
        
        # Non-critical error should NOT set last_error (lets user choose different format)
        assert "last_error" not in result or result.get("last_error") is None
        assert "next_prompt" in result


class TestMapAnswersNodeErrorHandling:
    """Tests for error handling in map_answers_node."""

    def test_unexpected_error_sets_last_error(self):
        """Unexpected error sets last_error for routing to error_handler."""
        from src.nodes.map_answers_node import map_answers_node
        
        state: AgentState = {
            "interview_data": None,  # Will cause issues
            "_field_mappings": [{"field_name": "position_title", "parsed_value": "Test"}],
        }
        
        with patch("src.nodes.map_answers_node._get_or_create_interview_data") as mock_get:
            mock_get.side_effect = RuntimeError("Unexpected error")
            result = map_answers_node(state)
        
        assert "last_error" in result
        assert "RuntimeError" in result["last_error"]
        assert "map_answers" in result["last_error"]


class TestAnswerQuestionNodeErrorHandling:
    """Tests for error handling in answer_question_node."""

    @pytest.mark.asyncio
    async def test_missing_api_key_sets_last_error(self):
        """Missing API key sets last_error for routing to error_handler."""
        from src.nodes.answer_question_node import answer_question_node_async
        
        state: AgentState = {
            "pending_question": "What is an FES factor?",
        }
        
        with patch.dict("os.environ", {}, clear=True):
            with patch("os.getenv", return_value=None):
                result = await answer_question_node_async(state)
        
        assert "last_error" in result
        assert "ConfigurationError" in result["last_error"]

    @pytest.mark.asyncio
    async def test_llm_error_sets_last_error(self):
        """LLM error sets last_error for routing to error_handler."""
        from src.nodes.answer_question_node import answer_question_node_async
        
        state: AgentState = {
            "pending_question": "What is an FES factor?",
        }
        
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch("src.nodes.answer_question_node.answer_question_with_llm") as mock_llm:
                mock_llm.side_effect = Exception("LLM connection failed")
                result = await answer_question_node_async(state)
        
        assert "last_error" in result
        assert "answer_question" in result["last_error"]


class TestGenerateElementNodeErrorHandling:
    """Tests for error handling in generate_element_node."""

    @pytest.mark.asyncio
    async def test_llm_error_sets_last_error(self):
        """LLM error during generation sets last_error."""
        from src.nodes.generate_element_node import generate_element_node
        
        # Create a minimal valid state with draft elements
        # Use duties_overview which requires LLM generation (tier="llm")
        state: AgentState = {
            "current_element_index": 0,
            "draft_elements": [
                {
                    "name": "duties_overview",
                    "display_name": "Duties Overview",
                    "content": "",
                    "status": "pending",
                    "revision_count": 0,
                    "prerequisites": [],
                }
            ],
            "interview_data": {
                "position_title": {"value": "Test Position", "is_set": True},
                "series": {"value": "2210", "is_set": True},
                "grade": {"value": "13", "is_set": True},
                "organization": {"value": ["Agency", "Office"], "is_set": True},
                "reports_to": {"value": "Supervisor", "is_set": True},
                "is_supervisor": {"value": False, "is_set": True},
                "major_duties": {"value": ["Duty 1"], "is_set": True},
            },
        }
        
        with patch("src.nodes.generate_element_node.traced_llm_call") as mock_llm:
            mock_llm.side_effect = Exception("LLM timeout")
            result = await generate_element_node(state)
        
        assert "last_error" in result
        assert "generate_element" in result["last_error"]


class TestErrorRecoveryIntegration:
    """Integration tests for error recovery flow."""

    def test_error_routing_flow(self):
        """Test that error flows from node → routing → error_handler → user_input."""
        from src.nodes.routing import route_after_draft_response, route_by_intent
        
        # Simulate state after a node sets an error
        state_with_error: AgentState = {
            "last_error": "some_node: SomeError: Something failed",
            "draft_elements": [],
            "phase": "drafting",
        }
        
        # Various routing functions should detect error and route to error_handler
        assert route_after_draft_response(state_with_error) == "error_handler"
        assert route_by_intent(state_with_error) == "error_handler"
        
        # Error handler clears error and provides recovery message
        result = error_handler_node(state_with_error)
        assert result.get("last_error") is None
        assert len(result.get("messages", [])) == 1
        
        # Route after error goes to user_input for recovery
        assert route_after_error(state_with_error) == "user_input"
