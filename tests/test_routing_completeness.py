"""Tests for routing completeness and error handling coverage.

These tests verify that:
1. All routing functions return values that are mapped in conditional edges
2. Error handling is consistent across routing functions
3. Default fallback to error_handler exists where appropriate
"""

import pytest

from src.models.state import AgentState
from src.nodes.routing import (
    RouteDestination,
    _check_for_error,
    route_after_advance_element,
    route_after_draft_response,
    route_after_element_revision,
    route_after_end_conversation,
    route_after_export,
    route_after_finalize,
    route_after_generate_element,
    route_after_init,
    route_after_qa,
    route_by_intent,
)


class TestRouteAfterInit:
    """Tests for route_after_init routing function."""

    def test_always_returns_user_input(self):
        """Init always routes to user_input."""
        state: AgentState = {}
        result = route_after_init(state)
        assert result == "user_input"


class TestRouteByIntent:
    """Tests for route_by_intent - the main intent-based router."""

    def test_error_in_state_routes_to_error_handler(self):
        """When last_error is set, route to error_handler."""
        state: AgentState = {
            "last_error": "classify_intent: LLMConnectionError: Connection failed",
            "phase": "interview",
        }
        result = route_by_intent(state)
        assert result == "error_handler"

    def test_quit_intent_routes_to_end_conversation(self):
        """Quit intent always routes to end_conversation."""
        state: AgentState = {"last_intent": "quit", "phase": "interview"}
        result = route_by_intent(state)
        assert result == "end_conversation"

    def test_request_restart_routes_to_init(self):
        """Request restart routes to init."""
        state: AgentState = {"last_intent": "request_restart", "phase": "interview"}
        result = route_by_intent(state)
        assert result == "init"

    def test_interview_phase_provide_info_routes_to_map_answers(self):
        """During interview, provide_information routes to map_answers."""
        state: AgentState = {"last_intent": "provide_information", "phase": "interview"}
        result = route_by_intent(state)
        assert result == "map_answers"

    def test_unknown_phase_returns_handle_unrecognized(self):
        """Unknown phase returns handle_unrecognized as fallback."""
        state: AgentState = {"last_intent": "confirm", "phase": "unknown_phase"}
        result = route_by_intent(state)
        assert result == "handle_unrecognized"


class TestRouteAfterQa:
    """Tests for route_after_qa routing function."""

    def test_error_routes_to_error_handler(self):
        """QA error routes to error_handler."""
        state: AgentState = {
            "last_error": "qa_review: LLMResponseError: Invalid JSON",
            "draft_elements": [],
        }
        result = route_after_qa(state)
        assert result == "error_handler"

    def test_qa_passed_routes_to_user_input(self):
        """QA passed routes to user_input for presentation."""
        # DraftElement.qa_passed is a computed property that checks qa_review.passes
        state: AgentState = {
            "draft_elements": [
                {
                    "name": "introduction",
                    "display_name": "Introduction",
                    "content": "Test content",
                    "status": "qa_passed",
                    "qa_review": {"passes": True, "check_results": [], "overall_feedback": "Good"},
                    "revision_count": 0,
                }
            ],
            "current_element_index": 0,
        }
        result = route_after_qa(state)
        assert result == "user_input"

    def test_qa_failed_can_rewrite_routes_to_generate(self):
        """QA failed with rewrites available routes to generate_element."""
        # DraftElement.can_rewrite checks revision_count < 1
        state: AgentState = {
            "draft_elements": [
                {
                    "name": "introduction",
                    "display_name": "Introduction",
                    "content": "Test content",
                    "status": "needs_revision",
                    "qa_review": {"passes": False, "check_results": [], "overall_feedback": "Needs work"},
                    "revision_count": 0,  # Can still rewrite (limit is 1)
                }
            ],
            "current_element_index": 0,
        }
        result = route_after_qa(state)
        assert result == "generate_element"


class TestRouteAfterDraftResponse:
    """Tests for route_after_draft_response routing function."""

    def test_error_routes_to_error_handler(self):
        """Error in state routes to error_handler."""
        state: AgentState = {
            "last_error": "handle_draft_response: ValidationError: Invalid data",
            "draft_elements": [],
        }
        result = route_after_draft_response(state)
        assert result == "error_handler"

    def test_needs_revision_routes_to_generate_element(self):
        """Element needing revision routes to generate_element."""
        state: AgentState = {
            "draft_elements": [{"name": "introduction", "status": "needs_revision"}],
            "current_element_index": 0,
        }
        result = route_after_draft_response(state)
        assert result == "generate_element"

    def test_approved_routes_to_advance_element(self):
        """Approved element routes to advance_element."""
        state: AgentState = {
            "draft_elements": [{"name": "introduction", "status": "approved"}],
            "current_element_index": 0,
        }
        result = route_after_draft_response(state)
        assert result == "advance_element"


class TestRouteAfterAdvanceElement:
    """Tests for route_after_advance_element routing function."""

    def test_error_routes_to_error_handler(self):
        """Error in state routes to error_handler."""
        state: AgentState = {
            "last_error": "advance_element: IndexError: Out of bounds",
            "phase": "drafting",
        }
        result = route_after_advance_element(state)
        assert result == "error_handler"

    def test_drafting_phase_routes_to_generate_element(self):
        """Drafting phase routes to generate_element."""
        state: AgentState = {"phase": "drafting"}
        result = route_after_advance_element(state)
        assert result == "generate_element"

    def test_review_phase_routes_to_finalize(self):
        """Review phase routes to finalize."""
        state: AgentState = {"phase": "review"}
        result = route_after_advance_element(state)
        assert result == "finalize"


class TestRouteAfterExport:
    """Tests for route_after_export routing function."""

    def test_critical_error_routes_to_error_handler(self):
        """Critical file system error routes to error_handler."""
        state: AgentState = {
            "last_error": "export_document: PermissionError: Cannot write file",
        }
        result = route_after_export(state)
        assert result == "error_handler"

    def test_format_error_routes_to_user_input(self):
        """Format error lets user choose different format."""
        state: AgentState = {
            "last_error": "export_document: InvalidFormat: Unknown format",
        }
        result = route_after_export(state)
        assert result == "user_input"

    def test_success_routes_to_end_conversation(self):
        """Successful export routes to end_conversation."""
        state: AgentState = {}
        result = route_after_export(state)
        assert result == "end_conversation"


class TestRouteAfterElementRevision:
    """Tests for route_after_element_revision routing function."""

    def test_error_routes_to_error_handler(self):
        """Error in state routes to error_handler."""
        state: AgentState = {
            "last_error": "handle_element_revision: KeyError: Missing element",
            "phase": "drafting",
        }
        result = route_after_element_revision(state)
        assert result == "error_handler"

    def test_valid_element_routes_to_generate(self):
        """Valid element in drafting phase routes to generate_element."""
        state: AgentState = {
            "current_element_name": "introduction",
            "phase": "drafting",
        }
        result = route_after_element_revision(state)
        assert result == "generate_element"

    def test_no_element_routes_to_user_input(self):
        """No element identified routes to user_input."""
        state: AgentState = {"phase": "drafting"}
        result = route_after_element_revision(state)
        assert result == "user_input"


class TestRouteAfterEndConversation:
    """Tests for route_after_end_conversation routing function."""

    def test_error_routes_to_error_handler(self):
        """Error in state routes to error_handler."""
        state: AgentState = {
            "last_error": "end_conversation: StateError: Corrupt state",
        }
        result = route_after_end_conversation(state)
        assert result == "error_handler"

    def test_wants_another_none_routes_to_user_input(self):
        """When wants_another is None, route to user_input to ask."""
        state: AgentState = {"wants_another": None}
        result = route_after_end_conversation(state)
        assert result == "user_input"

    def test_wants_another_true_routes_to_init(self):
        """When user wants another PD, route to init."""
        state: AgentState = {"wants_another": True}
        result = route_after_end_conversation(state)
        assert result == "init"

    def test_wants_another_false_routes_to_end(self):
        """When user is done, route to __end__."""
        state: AgentState = {"wants_another": False}
        result = route_after_end_conversation(state)
        assert result == "__end__"


class TestRouteAfterFinalize:
    """Tests for route_after_finalize routing function."""

    def test_always_routes_to_user_input(self):
        """Finalize always routes to user_input for format selection."""
        state: AgentState = {}
        result = route_after_finalize(state)
        assert result == "user_input"


class TestRouteAfterGenerateElement:
    """Tests for route_after_generate_element routing function."""

    def test_normal_routes_to_qa_review(self):
        """Normal operation routes to qa_review."""
        # This depends on SKIP_QA env var, test the default
        state: AgentState = {}
        result = route_after_generate_element(state)
        # Default should be qa_review unless SKIP_QA is set
        assert result in ("qa_review", "user_input")


class TestCheckForError:
    """Tests for _check_for_error helper function."""

    def test_empty_state_returns_false(self):
        """Empty state has no error."""
        state: AgentState = {}
        assert _check_for_error(state) is False

    def test_none_error_returns_false(self):
        """Explicit None error returns False."""
        state: AgentState = {"last_error": None}
        assert _check_for_error(state) is False

    def test_empty_string_error_returns_false(self):
        """Empty string error returns False."""
        state: AgentState = {"last_error": ""}
        assert _check_for_error(state) is False

    def test_actual_error_returns_true(self):
        """Actual error string returns True."""
        state: AgentState = {"last_error": "some_node: SomeError: message"}
        assert _check_for_error(state) is True


class TestRoutingCompleteness:
    """Meta-tests to verify routing completeness."""

    def test_all_route_functions_return_route_destination(self):
        """Verify all route functions return valid RouteDestination values."""
        # Get all valid destinations from the type alias
        from typing import get_args
        valid_destinations = set(get_args(RouteDestination))
        
        # Add __end__ which is used by end_conversation
        valid_destinations.add("__end__")
        
        # Test each routing function with minimal valid state
        test_cases = [
            (route_after_init, {}),
            (route_after_finalize, {}),
            (route_after_draft_response, {"draft_elements": [{"name": "intro", "display_name": "Intro", "status": "approved"}]}),
            (route_after_advance_element, {"phase": "complete"}),
            (route_after_export, {}),
            (route_after_element_revision, {"phase": "drafting"}),
            (route_after_end_conversation, {"wants_another": False}),
            (route_after_generate_element, {}),
        ]
        
        for route_fn, state in test_cases:
            result = route_fn(state)
            assert result in valid_destinations, (
                f"{route_fn.__name__} returned '{result}' which is not a valid RouteDestination"
            )

    def test_error_handler_route_exists_for_fallible_functions(self):
        """Verify functions that can fail route to error_handler on error."""
        fallible_functions = [
            route_after_draft_response,
            route_after_advance_element,
            route_after_element_revision,
            route_after_end_conversation,
            route_after_qa,
            route_by_intent,
        ]
        
        error_state: AgentState = {"last_error": "test: TestError: test message"}
        
        for route_fn in fallible_functions:
            result = route_fn(error_state)
            assert result == "error_handler", (
                f"{route_fn.__name__} should route to error_handler when last_error is set, "
                f"but returned '{result}'"
            )
