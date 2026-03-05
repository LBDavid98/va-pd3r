"""Tests for the error handler node."""

import pytest

from src.nodes.error_handler_node import (
    error_handler_node,
    route_after_error,
    _extract_error_type,
    _get_user_message,
    ERROR_MESSAGES,
    DEFAULT_ERROR_MESSAGE,
)


class TestExtractErrorType:
    """Tests for error type extraction from error strings."""

    def test_extracts_type_from_standard_format(self):
        """Should extract error type from 'node: ErrorType: message' format."""
        error = "intent_classification: LLMConnectionError: Failed to connect"
        
        result = _extract_error_type(error)
        
        assert result == "LLMConnectionError"

    def test_handles_missing_message(self):
        """Should work when there's no message after the type."""
        error = "node: ErrorType"
        
        result = _extract_error_type(error)
        
        assert result == "ErrorType"

    def test_returns_empty_for_empty_string(self):
        """Should return empty string for empty input."""
        result = _extract_error_type("")
        
        assert result == ""

    def test_returns_empty_for_none(self):
        """Should return empty string for None input."""
        result = _extract_error_type(None)
        
        assert result == ""

    def test_returns_empty_for_malformed(self):
        """Should return empty string for malformed error string."""
        error = "no colon here"
        
        result = _extract_error_type(error)
        
        assert result == ""


class TestGetUserMessage:
    """Tests for user message retrieval."""

    def test_returns_known_error_message(self):
        """Should return specific message for known error types."""
        error = "node: LLMConnectionError: details"
        
        result = _get_user_message(error)
        
        assert result == ERROR_MESSAGES["LLMConnectionError"]

    def test_returns_default_for_unknown_type(self):
        """Should return default message for unknown error types."""
        error = "node: UnknownError: details"
        
        result = _get_user_message(error)
        
        assert result == DEFAULT_ERROR_MESSAGE

    def test_returns_default_for_empty_string(self):
        """Should return default message for empty error string."""
        result = _get_user_message("")
        
        assert result == DEFAULT_ERROR_MESSAGE


class TestErrorHandlerNode:
    """Tests for the error handler node function."""

    def test_clears_error_from_state(self):
        """Should set last_error to None in returned state."""
        state = {
            "last_error": "node: LLMConnectionError: Failed",
            "messages": [],
            "phase": "interview",
        }
        
        result = error_handler_node(state)
        
        assert result["last_error"] is None

    def test_adds_recovery_message(self):
        """Should add an AI message with recovery text."""
        state = {
            "last_error": "node: LLMRateLimitError: Rate limited",
            "messages": [],
            "phase": "interview",
        }
        
        result = error_handler_node(state)
        
        assert len(result["messages"]) == 1
        assert "overwhelmed" in result["messages"][0].content

    def test_handles_no_error_gracefully(self):
        """Should return empty dict when no error is present."""
        state = {
            "last_error": None,
            "messages": [],
            "phase": "interview",
        }
        
        result = error_handler_node(state)
        
        assert result == {}

    def test_uses_correct_message_for_each_error_type(self):
        """Should use appropriate message for each known error type."""
        for error_type, expected_message in ERROR_MESSAGES.items():
            state = {
                "last_error": f"node: {error_type}: details",
                "messages": [],
            }
            
            result = error_handler_node(state)
            
            assert result["messages"][0].content == expected_message


class TestRouteAfterError:
    """Tests for error handler routing."""

    def test_always_routes_to_user_input(self):
        """Should always route to user_input for recovery."""
        state = {"phase": "interview", "last_error": None}
        
        result = route_after_error(state)
        
        assert result == "user_input"

    def test_routes_to_user_input_regardless_of_phase(self):
        """Should route to user_input regardless of current phase."""
        for phase in ["init", "interview", "drafting", "review", "complete"]:
            state = {"phase": phase}
            
            result = route_after_error(state)
            
            assert result == "user_input"
