"""Tests for error handling and recovery (4.5)."""

import pytest
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from src.exceptions import (
    CheckpointerError,
    FieldValidationError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMResponseError,
    LLMRetryExhaustedError,
    LLMTimeoutError,
    MissingStateFieldError,
    NodeException,
    NodeExecutionError,
    PD3rException,
    get_user_message,
    is_retryable,
)
from src.models.state import AgentState
from src.utils.recovery import (
    create_recovery_response,
    handle_llm_error_in_node,
    safe_state_access,
    wrap_node_with_recovery,
)


# =============================================================================
# Exception Tests
# =============================================================================

class TestPD3rExceptionHierarchy:
    """Test the exception class hierarchy."""
    
    def test_base_exception_with_message(self):
        """Base exception stores message."""
        exc = PD3rException("Something went wrong")
        assert str(exc) == "Something went wrong"
        assert exc.message == "Something went wrong"
        assert exc.context == {}
    
    def test_base_exception_with_context(self):
        """Base exception stores context dict."""
        exc = PD3rException("Error", context={"key": "value"})
        assert "key" in exc.context
        assert exc.context["key"] == "value"
        assert "Context:" in str(exc)
    
    def test_llm_exception_inheritance(self):
        """LLM exceptions inherit from PD3rException."""
        exc = LLMConnectionError("Connection failed")
        assert isinstance(exc, PD3rException)
        assert hasattr(exc, "user_message")
    
    def test_validation_exception_with_field_info(self):
        """FieldValidationError stores field details."""
        exc = FieldValidationError(
            field_name="series",
            provided_value="invalid",
            error_message="Please enter a valid 4-digit series code.",
        )
        assert exc.field_name == "series"
        assert exc.provided_value == "invalid"
        assert "Hmm" in exc.user_message
    
    def test_retry_exhausted_exception(self):
        """LLMRetryExhaustedError stores attempt info."""
        original = ValueError("Original error")
        exc = LLMRetryExhaustedError(
            message="Failed after 3 attempts",
            attempts=3,
            last_error=original,
        )
        assert exc.attempts == 3
        assert exc.last_error is original
    
    def test_missing_state_field_error(self):
        """MissingStateFieldError stores field name."""
        exc = MissingStateFieldError(
            field_name="interview_data",
            expected_phase="interview",
        )
        assert exc.field_name == "interview_data"
        assert "interview_data" in str(exc)


class TestIsRetryable:
    """Test is_retryable function."""
    
    def test_connection_error_is_retryable(self):
        """Connection errors should be retried."""
        assert is_retryable(LLMConnectionError("Failed"))
    
    def test_rate_limit_is_retryable(self):
        """Rate limit errors should be retried."""
        assert is_retryable(LLMRateLimitError("Too many requests"))
    
    def test_timeout_is_retryable(self):
        """Timeout errors should be retried."""
        assert is_retryable(LLMTimeoutError("Request timed out"))
    
    def test_response_error_not_retryable(self):
        """Response errors should not be retried."""
        assert not is_retryable(LLMResponseError("Invalid JSON"))
    
    def test_validation_error_not_retryable(self):
        """Validation errors should not be retried."""
        exc = FieldValidationError("field", "value", "Invalid")
        assert not is_retryable(exc)
    
    def test_generic_exception_not_retryable(self):
        """Generic exceptions should not be retried."""
        assert not is_retryable(ValueError("Something"))


class TestGetUserMessage:
    """Test get_user_message function."""
    
    def test_gets_user_message_from_exception(self):
        """Should return user_message attribute."""
        exc = LLMConnectionError("Internal error")
        msg = get_user_message(exc)
        assert "trouble connecting" in msg.lower()
    
    def test_fallback_for_unknown_exception(self):
        """Should return fallback for unknown exceptions."""
        exc = ValueError("Unknown error")
        msg = get_user_message(exc)
        assert "unexpected" in msg.lower()


# =============================================================================
# Recovery Utility Tests
# =============================================================================

class TestCreateRecoveryResponse:
    """Test create_recovery_response function."""
    
    def test_creates_response_with_message(self):
        """Response includes AIMessage."""
        state: AgentState = {
            "messages": [],
            "phase": "interview",
            "interview_data": None,
            "current_field": None,
            "missing_fields": [],
            "fields_needing_confirmation": [],
            "last_intent": None,
            "pending_question": None,
            "fes_evaluation": None,
            "draft_requirements": None,
            "draft_elements": [],
            "current_element_index": 0,
            "current_element_name": None,
            "should_end": False,
            "next_prompt": "",
            "wants_another": None,
            "is_restart": False,
            "validation_error": None,
            "last_error": None,
        }
        
        exc = LLMConnectionError("Failed")
        response = create_recovery_response(exc, "test_node", state)
        
        assert "messages" in response
        assert "last_error" in response
        assert isinstance(response["messages"][0], AIMessage)
    
    def test_uses_fallback_message(self):
        """Uses provided fallback message."""
        state: AgentState = {
            "messages": [],
            "phase": "interview",
            "interview_data": None,
            "current_field": None,
            "missing_fields": [],
            "fields_needing_confirmation": [],
            "last_intent": None,
            "pending_question": None,
            "fes_evaluation": None,
            "draft_requirements": None,
            "draft_elements": [],
            "current_element_index": 0,
            "current_element_name": None,
            "should_end": False,
            "next_prompt": "",
            "wants_another": None,
            "is_restart": False,
            "validation_error": None,
            "last_error": None,
        }
        
        exc = ValueError("Error")
        response = create_recovery_response(
            exc, "test_node", state, fallback_message="Custom message"
        )
        
        assert response["messages"][0].content == "Custom message"


class TestHandleLLMErrorInNode:
    """Test handle_llm_error_in_node function."""
    
    def test_handles_retry_exhausted(self):
        """Provides specific message for retry exhaustion."""
        state: AgentState = {
            "messages": [],
            "phase": "drafting",
            "interview_data": None,
            "current_field": None,
            "missing_fields": [],
            "fields_needing_confirmation": [],
            "last_intent": None,
            "pending_question": None,
            "fes_evaluation": None,
            "draft_requirements": None,
            "draft_elements": [],
            "current_element_index": 0,
            "current_element_name": None,
            "should_end": False,
            "next_prompt": "",
            "wants_another": None,
            "is_restart": False,
            "validation_error": None,
            "last_error": None,
        }
        
        exc = LLMRetryExhaustedError("Failed", attempts=3)
        response = handle_llm_error_in_node(
            exc, "generate_element", state, "generate the draft"
        )
        
        assert "tried several times" in response["messages"][0].content.lower()


class TestSafeStateAccess:
    """Test safe_state_access function."""
    
    def test_returns_value_when_present(self):
        """Returns value when key exists."""
        state: AgentState = {
            "messages": [],
            "phase": "interview",
            "interview_data": {"test": "data"},
            "current_field": None,
            "missing_fields": [],
            "fields_needing_confirmation": [],
            "last_intent": None,
            "pending_question": None,
            "fes_evaluation": None,
            "draft_requirements": None,
            "draft_elements": [],
            "current_element_index": 0,
            "current_element_name": None,
            "should_end": False,
            "next_prompt": "",
            "wants_another": None,
            "is_restart": False,
            "validation_error": None,
            "last_error": None,
        }
        
        result = safe_state_access(state, "interview_data")
        assert result == {"test": "data"}
    
    def test_returns_default_when_missing(self):
        """Returns default when key is None."""
        state: AgentState = {
            "messages": [],
            "phase": "interview",
            "interview_data": None,
            "current_field": None,
            "missing_fields": [],
            "fields_needing_confirmation": [],
            "last_intent": None,
            "pending_question": None,
            "fes_evaluation": None,
            "draft_requirements": None,
            "draft_elements": [],
            "current_element_index": 0,
            "current_element_name": None,
            "should_end": False,
            "next_prompt": "",
            "wants_another": None,
            "is_restart": False,
            "validation_error": None,
            "last_error": None,
        }
        
        result = safe_state_access(state, "interview_data", default={})
        assert result == {}
    
    def test_raises_when_error_on_missing(self):
        """Raises MissingStateFieldError when requested."""
        state: AgentState = {
            "messages": [],
            "phase": "interview",
            "interview_data": None,
            "current_field": None,
            "missing_fields": [],
            "fields_needing_confirmation": [],
            "last_intent": None,
            "pending_question": None,
            "fes_evaluation": None,
            "draft_requirements": None,
            "draft_elements": [],
            "current_element_index": 0,
            "current_element_name": None,
            "should_end": False,
            "next_prompt": "",
            "wants_another": None,
            "is_restart": False,
            "validation_error": None,
            "last_error": None,
        }
        
        with pytest.raises(MissingStateFieldError):
            safe_state_access(state, "interview_data", error_on_missing=True)


class TestWrapNodeWithRecovery:
    """Test wrap_node_with_recovery decorator."""
    
    def test_passes_through_on_success(self):
        """Returns normal result when no error."""
        @wrap_node_with_recovery
        def success_node(state):
            return {"messages": [AIMessage(content="Success")]}
        
        state: AgentState = {
            "messages": [],
            "phase": "interview",
            "interview_data": None,
            "current_field": None,
            "missing_fields": [],
            "fields_needing_confirmation": [],
            "last_intent": None,
            "pending_question": None,
            "fes_evaluation": None,
            "draft_requirements": None,
            "draft_elements": [],
            "current_element_index": 0,
            "current_element_name": None,
            "should_end": False,
            "next_prompt": "",
            "wants_another": None,
            "is_restart": False,
            "validation_error": None,
            "last_error": None,
        }
        
        result = success_node(state)
        assert result["messages"][0].content == "Success"
    
    def test_catches_pd3r_exception(self):
        """Catches PD3rException and returns recovery response."""
        @wrap_node_with_recovery
        def failing_node(state):
            raise LLMConnectionError("Connection failed")
        
        state: AgentState = {
            "messages": [],
            "phase": "interview",
            "interview_data": None,
            "current_field": None,
            "missing_fields": [],
            "fields_needing_confirmation": [],
            "last_intent": None,
            "pending_question": None,
            "fes_evaluation": None,
            "draft_requirements": None,
            "draft_elements": [],
            "current_element_index": 0,
            "current_element_name": None,
            "should_end": False,
            "next_prompt": "",
            "wants_another": None,
            "is_restart": False,
            "validation_error": None,
            "last_error": None,
        }
        
        result = failing_node(state)
        assert "messages" in result
        assert "last_error" in result
    
    def test_catches_generic_exception(self):
        """Catches generic exception with fallback message."""
        @wrap_node_with_recovery
        def generic_fail_node(state):
            raise ValueError("Unexpected error")
        
        state: AgentState = {
            "messages": [],
            "phase": "interview",
            "interview_data": None,
            "current_field": None,
            "missing_fields": [],
            "fields_needing_confirmation": [],
            "last_intent": None,
            "pending_question": None,
            "fes_evaluation": None,
            "draft_requirements": None,
            "draft_elements": [],
            "current_element_index": 0,
            "current_element_name": None,
            "should_end": False,
            "next_prompt": "",
            "wants_another": None,
            "is_restart": False,
            "validation_error": None,
            "last_error": None,
        }
        
        result = generic_fail_node(state)
        assert "unexpected" in result["messages"][0].content.lower()


# =============================================================================
# Validation Error Flow Tests
# =============================================================================

class TestValidationErrorInMapAnswers:
    """Test validation error handling in map_answers_node."""
    
    def test_invalid_series_sets_validation_error(self):
        """Invalid series code sets validation_error in state."""
        from src.nodes.map_answers_node import map_answers_node
        
        state: AgentState = {
            "messages": [HumanMessage(content="Series: abc")],
            "phase": "interview",
            "interview_data": None,
            "current_field": "series",
            "missing_fields": ["series", "grade"],
            "fields_needing_confirmation": [],
            "last_intent": "provide_information",
            "pending_question": None,
            "fes_evaluation": None,
            "draft_requirements": None,
            "draft_elements": [],
            "current_element_index": 0,
            "current_element_name": None,
            "should_end": False,
            "next_prompt": "",
            "wants_another": None,
            "is_restart": False,
            "validation_error": None,
            "last_error": None,
            "_field_mappings": [
                {
                    "field_name": "series",
                    "extracted_value": "abc",
                    "parsed_value": "abc",
                    "raw_input": "Series: abc",
                    "needs_confirmation": False,
                }
            ],
        }
        
        result = map_answers_node(state)
        
        # Should have validation error set
        assert result.get("validation_error") is not None
        assert "4-digit" in result["validation_error"]
    
    def test_valid_series_clears_validation_error(self):
        """Valid series code has no validation error."""
        from src.nodes.map_answers_node import map_answers_node
        
        state: AgentState = {
            "messages": [HumanMessage(content="Series: 2210")],
            "phase": "interview",
            "interview_data": None,
            "current_field": "series",
            "missing_fields": ["series", "grade"],
            "fields_needing_confirmation": [],
            "last_intent": "provide_information",
            "pending_question": None,
            "fes_evaluation": None,
            "draft_requirements": None,
            "draft_elements": [],
            "current_element_index": 0,
            "current_element_name": None,
            "should_end": False,
            "next_prompt": "",
            "wants_another": None,
            "is_restart": False,
            "validation_error": None,
            "last_error": None,
            "_field_mappings": [
                {
                    "field_name": "series",
                    "extracted_value": "2210",
                    "parsed_value": "2210",
                    "raw_input": "Series: 2210",
                    "needs_confirmation": False,
                }
            ],
        }
        
        result = map_answers_node(state)
        
        # Should have no validation error
        assert result.get("validation_error") is None or result["validation_error"] is None


class TestValidationErrorDisplay:
    """Test validation error display in prepare_next_node."""
    
    def test_validation_error_shown_in_prompt(self):
        """Validation error is displayed when re-prompting."""
        from src.nodes.prepare_next_node import prepare_next_node
        
        state: AgentState = {
            "messages": [],
            "phase": "interview",
            "interview_data": None,
            "current_field": "series",
            "missing_fields": ["series"],
            "fields_needing_confirmation": [],
            "last_intent": "provide_information",
            "pending_question": None,
            "fes_evaluation": None,
            "draft_requirements": None,
            "draft_elements": [],
            "current_element_index": 0,
            "current_element_name": None,
            "should_end": False,
            "next_prompt": "",
            "wants_another": None,
            "is_restart": False,
            "validation_error": "Please enter a valid 4-digit series code.",
            "last_error": None,
        }
        
        result = prepare_next_node(state)
        
        # Should include validation error in prompt
        assert "invalid" in result["next_prompt"].lower()
        assert "4-digit" in result["next_prompt"]
        # Should clear the validation error
        assert result.get("validation_error") is None


# =============================================================================
# Checkpointer Error Tests
# =============================================================================

class TestCheckpointerErrorHandling:
    """Test checkpointer error handling."""
    
    def test_checkpointer_error_exception(self):
        """CheckpointerError has user message."""
        exc = CheckpointerError("Failed to save state")
        assert hasattr(exc, "user_message")
        assert "trouble saving" in exc.user_message.lower()
    
    def test_safe_checkpointer_handles_put_error(self):
        """SafeCheckpointer handles put errors gracefully."""
        from src.graphs.main_graph import SafeCheckpointer
        
        mock_checkpointer = MagicMock()
        mock_checkpointer.put.side_effect = Exception("Disk full")
        
        safe = SafeCheckpointer(mock_checkpointer)
        result = safe.put("key", "value")
        
        # Should not raise, return None instead
        assert result is None
        assert safe.last_error is not None
        assert "Disk full" in safe.last_error
    
    def test_safe_checkpointer_handles_get_error(self):
        """SafeCheckpointer handles get errors gracefully."""
        from src.graphs.main_graph import SafeCheckpointer
        
        mock_checkpointer = MagicMock()
        mock_checkpointer.get.side_effect = Exception("Corrupted")
        
        safe = SafeCheckpointer(mock_checkpointer)
        result = safe.get("key")
        
        assert result is None
        assert safe.last_error is not None
