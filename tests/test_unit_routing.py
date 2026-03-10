"""Unit tests for routing logic."""

import pytest

from src.nodes.routing import (
    route_after_advance_element,
    route_after_draft_response,
    route_after_init,
    route_after_qa,
    route_by_intent,
    route_should_end,
)


class TestRouteByIntent:
    """Tests for main routing function."""

    def test_quit_routes_to_end(self):
        """Quit intent always goes to end_conversation."""
        state = {"last_intent": "quit", "phase": "interview"}

        result = route_by_intent(state)

        assert result == "end_conversation"

    def test_restart_routes_to_init(self):
        """Restart intent always goes to init."""
        state = {"last_intent": "request_restart", "phase": "interview"}

        result = route_by_intent(state)

        assert result == "init"

    def test_quit_takes_precedence_over_phase(self):
        """System commands take precedence over phase routing."""
        for phase in ["init", "interview", "drafting", "review"]:
            state = {"last_intent": "quit", "phase": phase}
            assert route_by_intent(state) == "end_conversation"

    def test_error_routes_to_error_handler(self):
        """Error in state routes to error_handler."""
        state = {
            "last_intent": "provide_information",
            "phase": "interview",
            "last_error": "node: SomeError: details",
        }

        result = route_by_intent(state)

        assert result == "error_handler"

    def test_error_takes_precedence_over_intent(self):
        """Error handling takes precedence over normal intent routing."""
        for phase in ["init", "interview", "drafting", "review", "complete"]:
            state = {
                "last_intent": "confirm",
                "phase": phase,
                "last_error": "node: Error: msg",
            }
            assert route_by_intent(state) == "error_handler"


class TestInitPhaseRouting:
    """Tests for routing during init phase."""

    def test_confirm_goes_to_start_interview(self):
        """Confirm in init phase starts interview."""
        state = {"last_intent": "confirm", "phase": "init"}

        result = route_by_intent(state)

        assert result == "start_interview"

    def test_provide_info_with_mappings_goes_to_map_answers(self):
        """Providing info with field mappings routes to map_answers."""
        state = {
            "last_intent": "provide_information",
            "phase": "init",
            "_field_mappings": [{"field_name": "position_title", "parsed_value": "Analyst"}],
        }

        result = route_by_intent(state)

        assert result == "map_answers"

    def test_provide_info_without_mappings_starts_interview(self):
        """Providing info without field mappings starts interview (user is engaging)."""
        state = {"last_intent": "provide_information", "phase": "init"}

        result = route_by_intent(state)

        assert result == "start_interview"

    def test_reject_goes_to_end(self):
        """Reject in init phase ends conversation."""
        state = {"last_intent": "reject", "phase": "init"}

        result = route_by_intent(state)

        assert result == "end_conversation"

    def test_question_goes_to_answer(self):
        """Question in init phase routes to answer_question."""
        state = {"last_intent": "ask_question", "phase": "init"}

        result = route_by_intent(state)

        assert result == "answer_question"


class TestInterviewPhaseRouting:
    """Tests for routing during interview phase."""

    def test_provide_info_goes_to_map_answers(self):
        """Providing info in interview routes to map_answers."""
        state = {
            "last_intent": "provide_information",
            "phase": "interview",
            "fields_needing_confirmation": [],
        }

        result = route_by_intent(state)

        assert result == "map_answers"

    def test_question_goes_to_answer(self):
        """Question in interview routes to answer_question."""
        state = {
            "last_intent": "ask_question",
            "phase": "interview",
            "fields_needing_confirmation": [],
        }

        result = route_by_intent(state)

        assert result == "answer_question"

    def test_confirm_with_pending_fields_goes_to_map(self):
        """Confirm with fields needing confirmation routes to map."""
        state = {
            "last_intent": "confirm",
            "phase": "interview",
            "fields_needing_confirmation": ["grade"],
        }

        result = route_by_intent(state)

        assert result == "map_answers"

    def test_confirm_without_pending_checks_complete(self):
        """Confirm without pending fields checks interview complete."""
        state = {
            "last_intent": "confirm",
            "phase": "interview",
            "fields_needing_confirmation": [],
        }

        result = route_by_intent(state)

        assert result == "check_interview_complete"

    def test_modify_goes_to_map_answers(self):
        """Modify intent routes to map_answers."""
        state = {
            "last_intent": "modify_answer",
            "phase": "interview",
            "fields_needing_confirmation": [],
        }

        result = route_by_intent(state)

        assert result == "map_answers"


class TestRequirementsPhaseRouting:
    """Tests for routing during requirements phase.
    
    The requirements phase is reached when the interview is complete.
    User has seen the summary and must confirm before FES evaluation.
    """

    def test_question_goes_to_answer(self):
        """Question in requirements phase routes to answer_question."""
        state = {"last_intent": "ask_question", "phase": "requirements"}

        result = route_by_intent(state)

        assert result == "answer_question"

    def test_confirm_goes_to_evaluate_fes(self):
        """Confirm in requirements phase routes to evaluate_fes.
        
        This is the key transition: user confirms interview summary → start drafting.
        """
        state = {"last_intent": "confirm", "phase": "requirements"}

        result = route_by_intent(state)

        assert result == "evaluate_fes"

    def test_modify_goes_to_map_answers(self):
        """Modify in requirements phase routes back to map_answers.
        
        User wants to change something from the summary.
        """
        state = {"last_intent": "modify_answer", "phase": "requirements"}

        result = route_by_intent(state)

        assert result == "map_answers"

    def test_reject_goes_to_map_answers(self):
        """Reject in requirements phase routes back to map_answers.
        
        User disagrees with something in the summary.
        """
        state = {"last_intent": "reject", "phase": "requirements"}

        result = route_by_intent(state)

        assert result == "map_answers"

    def test_provide_info_goes_to_map_answers(self):
        """Provide info in requirements phase routes to map_answers.
        
        User providing additional info - treat as modification.
        """
        state = {"last_intent": "provide_information", "phase": "requirements"}

        result = route_by_intent(state)

        assert result == "map_answers"

    def test_unrecognized_goes_to_reprompt(self):
        """Unrecognized intent in requirements generates clarification."""
        state = {"last_intent": "unrecognized", "phase": "requirements"}

        result = route_by_intent(state)

        assert result == "reprompt"

    def test_system_commands_still_work(self):
        """System commands take precedence in requirements phase."""
        state = {"last_intent": "quit", "phase": "requirements"}
        assert route_by_intent(state) == "end_conversation"

        state = {"last_intent": "request_restart", "phase": "requirements"}
        assert route_by_intent(state) == "init"


class TestDraftingPhaseRouting:
    """Tests for routing during drafting phase."""

    def test_confirm_goes_to_handle_draft_response(self):
        """Confirm in drafting phase routes to handle_draft_response."""
        state = {"last_intent": "confirm", "phase": "drafting", "draft_elements": []}

        result = route_by_intent(state)

        assert result == "handle_draft_response"

    def test_reject_goes_to_handle_draft_response(self):
        """Reject in drafting phase routes to handle_draft_response."""
        state = {"last_intent": "reject", "phase": "drafting", "draft_elements": []}

        result = route_by_intent(state)

        assert result == "handle_draft_response"

    def test_question_goes_to_answer(self):
        """Question in drafting phase routes to answer_question."""
        state = {"last_intent": "ask_question", "phase": "drafting", "draft_elements": []}

        result = route_by_intent(state)

        assert result == "answer_question"

    def test_modify_goes_to_handle_element_revision(self):
        """Modify in drafting phase routes to handle_element_revision for LLM-based element identification."""
        state = {"last_intent": "modify_answer", "phase": "drafting", "draft_elements": []}

        result = route_by_intent(state)

        assert result == "handle_element_revision"

    def test_provide_info_goes_to_handle_element_revision(self):
        """Unsolicited info in drafting phase routes to handle_element_revision.

        This uses LLM to identify the target element rather than relying on stale current_element_index.
        """
        state = {
            "last_intent": "provide_information",
            "phase": "drafting",
            "draft_elements": [],
        }

        result = route_by_intent(state)

        assert result == "handle_element_revision"

    def test_unrecognized_goes_to_reprompt(self):
        """Unrecognized intent in drafting generates clarification."""
        state = {"last_intent": "unrecognized", "phase": "drafting", "draft_elements": []}

        result = route_by_intent(state)

        assert result == "reprompt"


class TestReviewPhaseRouting:
    """Tests for routing during review phase."""

    def test_confirm_goes_to_end_conversation(self):
        """Confirm in review phase finalizes and ends."""
        state = {"last_intent": "confirm", "phase": "review"}

        result = route_by_intent(state)

        assert result == "end_conversation"

    def test_provide_info_goes_to_handle_draft_response(self):
        """Unsolicited info in review phase routes to handle_draft_response.

        This prevents an infinite loop and treats info as feedback.
        """
        state = {"last_intent": "provide_information", "phase": "review"}

        result = route_by_intent(state)

        assert result == "handle_draft_response"

    def test_reject_goes_to_user_input(self):
        """Reject in review phase routes to user_input for clarification."""
        state = {"last_intent": "reject", "phase": "review"}

        result = route_by_intent(state)

        assert result == "user_input"

    def test_unrecognized_goes_to_user_input(self):
        """Unrecognized intent in review stays on user_input."""
        state = {"last_intent": "unrecognized", "phase": "review"}

        result = route_by_intent(state)

        assert result == "user_input"


class TestRouteAfterInit:
    """Tests for routing after init node."""

    def test_always_goes_to_user_input(self):
        """After init, always collect user input."""
        state = {"phase": "init"}

        result = route_after_init(state)

        assert result == "user_input"


class TestRouteShouldEnd:
    """Tests for should_end routing."""

    def test_should_end_true(self):
        """When should_end is True, go to end_conversation."""
        state = {"should_end": True}

        result = route_should_end(state)

        assert result == "end_conversation"

    def test_should_end_false(self):
        """When should_end is False, go to user_input."""
        state = {"should_end": False}

        result = route_should_end(state)

        assert result == "user_input"

    def test_should_end_missing(self):
        """When should_end is missing, default to user_input."""
        state = {}

        result = route_should_end(state)

        assert result == "user_input"


class TestRouteAfterDraftResponse:
    """Tests for routing after user responds to draft element."""

    def test_needs_revision_routes_to_generate(self):
        """When element needs revision, route to generate_element."""
        state = {
            "draft_elements": [
                {"element_type": "introduction", "status": "needs_revision"}
            ],
            "current_element_index": 0,
        }

        result = route_after_draft_response(state)

        assert result == "generate_element"

    def test_approved_routes_to_advance(self):
        """When element is approved, route to advance_element."""
        state = {
            "draft_elements": [
                {"element_type": "introduction", "status": "approved"}
            ],
            "current_element_index": 0,
        }

        result = route_after_draft_response(state)

        assert result == "advance_element"

    def test_empty_draft_elements_routes_to_advance(self):
        """When no draft elements exist, route to advance_element."""
        state = {
            "draft_elements": [],
            "current_element_index": 0,
        }

        result = route_after_draft_response(state)

        assert result == "advance_element"

    def test_index_out_of_bounds_routes_to_advance(self):
        """When index is out of bounds, route to advance_element."""
        state = {
            "draft_elements": [
                {"element_type": "introduction", "status": "needs_revision"}
            ],
            "current_element_index": 5,  # Out of bounds
        }

        result = route_after_draft_response(state)

        assert result == "advance_element"

    def test_missing_status_routes_to_advance(self):
        """When element has no status, route to advance_element."""
        state = {
            "draft_elements": [
                {"element_type": "introduction"}  # No status field
            ],
            "current_element_index": 0,
        }

        result = route_after_draft_response(state)

        assert result == "advance_element"

    def test_second_element_needs_revision(self):
        """Test routing with non-zero element index."""
        state = {
            "draft_elements": [
                {"element_type": "introduction", "status": "approved"},
                {"element_type": "duties", "status": "needs_revision"},
            ],
            "current_element_index": 1,
        }

        result = route_after_draft_response(state)

        assert result == "generate_element"


class TestRouteAfterAdvanceElement:
    """Tests for routing after advancing to next element."""

    def test_drafting_phase_routes_to_generate(self):
        """When still in drafting phase, route to generate_element."""
        state = {"phase": "drafting"}

        result = route_after_advance_element(state)

        assert result == "generate_element"

    def test_complete_phase_routes_to_end(self):
        """When drafting is complete, route to end_conversation."""
        state = {"phase": "complete"}

        result = route_after_advance_element(state)

        assert result == "end_conversation"

    def test_review_phase_routes_to_finalize(self):
        """When in review phase, route to finalize for final document assembly."""
        state = {"phase": "review"}

        result = route_after_advance_element(state)

        assert result == "finalize"

    def test_empty_phase_routes_to_end(self):
        """When phase is empty, route to end_conversation."""
        state = {"phase": ""}

        result = route_after_advance_element(state)

        assert result == "end_conversation"

    def test_missing_phase_routes_to_end(self):
        """When phase is missing, route to end_conversation."""
        state = {}

        result = route_after_advance_element(state)

        assert result == "end_conversation"


class TestPhaseTransitionSequence:
    """Tests for valid phase transition sequences."""

    def test_valid_phase_sequence_handles_questions(self):
        """Verify pre-review phases handle questions properly."""
        # These phases should route ask_question to answer_question
        question_phases = ["init", "interview", "requirements", "drafting"]

        for phase in question_phases:
            state = {"last_intent": "ask_question", "phase": phase}
            result = route_by_intent(state)
            assert result == "answer_question", f"Phase '{phase}' failed ask_question routing"

    def test_requirements_phase_exists(self):
        """Verify requirements phase doesn't fall through to unrecognized."""
        state = {"last_intent": "confirm", "phase": "requirements"}

        result = route_by_intent(state)

        # Should NOT route to handle_unrecognized
        assert result != "handle_unrecognized"

    def test_all_phases_handle_system_commands(self):
        """System commands work in all phases."""
        valid_phases = ["init", "interview", "requirements", "drafting", "review"]

        for phase in valid_phases:
            # Test quit
            state = {"last_intent": "quit", "phase": phase}
            assert route_by_intent(state) == "end_conversation", f"Quit failed in {phase}"

            # Test restart
            state = {"last_intent": "request_restart", "phase": phase}
            assert route_by_intent(state) == "init", f"Restart failed in {phase}"


class TestRouteAfterQA:
    """Tests for route_after_qa function - consolidated rewrite limit logic."""

    def _create_element_dict(
        self, 
        qa_passes: bool = True, 
        revision_count: int = 0
    ) -> dict:
        """Create a draft element dict for testing."""
        from src.models.draft import DraftElement, QAReview
        
        element = DraftElement(
            name="introduction",
            display_name="Introduction",
            content="Test content",
            status="drafted",
            revision_count=revision_count,
        )
        
        # Apply QA review if needed
        if qa_passes or not qa_passes:  # Always set a review
            review = QAReview(
                passes=qa_passes,
                check_results=[],
                overall_feedback="Test feedback",
                needs_rewrite=not qa_passes,
            )
            element.apply_qa_review(review)
        
        return element.model_dump()

    def test_qa_passed_routes_to_user_input(self):
        """When QA passes, route to user_input for approval."""
        element = self._create_element_dict(qa_passes=True, revision_count=0)
        state = {
            "draft_elements": [element],
            "current_element_index": 0,
        }

        result = route_after_qa(state)

        assert result == "user_input"

    def test_qa_failed_can_rewrite_routes_to_generate(self):
        """When QA fails but can rewrite (revision_count=0), route to generate_element."""
        element = self._create_element_dict(qa_passes=False, revision_count=0)
        state = {
            "draft_elements": [element],
            "current_element_index": 0,
        }

        result = route_after_qa(state)

        assert result == "generate_element"

    def test_qa_failed_hit_limit_routes_to_user_input(self):
        """When QA fails and hit rewrite limit (revision_count>=1), route to user_input."""
        element = self._create_element_dict(qa_passes=False, revision_count=1)
        state = {
            "draft_elements": [element],
            "current_element_index": 0,
        }

        result = route_after_qa(state)

        assert result == "user_input"

    def test_qa_failed_exceeded_limit_routes_to_user_input(self):
        """When QA fails and exceeded rewrite limit (revision_count>1), route to user_input."""
        element = self._create_element_dict(qa_passes=False, revision_count=2)
        state = {
            "draft_elements": [element],
            "current_element_index": 0,
        }

        result = route_after_qa(state)

        assert result == "user_input"

    def test_empty_draft_elements_routes_to_user_input(self):
        """When draft_elements is empty, route to user_input as fallback."""
        state = {
            "draft_elements": [],
            "current_element_index": 0,
        }

        result = route_after_qa(state)

        assert result == "user_input"

    def test_missing_draft_elements_routes_to_user_input(self):
        """When draft_elements is missing, route to user_input as fallback."""
        state = {}

        result = route_after_qa(state)

        assert result == "user_input"

    def test_index_out_of_bounds_routes_to_user_input(self):
        """When element index is out of bounds, route to user_input as fallback."""
        element = self._create_element_dict(qa_passes=False, revision_count=0)
        state = {
            "draft_elements": [element],
            "current_element_index": 5,  # Out of bounds
        }

        result = route_after_qa(state)

        assert result == "user_input"

    def test_error_in_state_routes_to_error_handler(self):
        """When last_error is set, route to error_handler for recovery."""
        element = self._create_element_dict(qa_passes=True, revision_count=0)
        state = {
            "draft_elements": [element],
            "current_element_index": 0,
            "last_error": "qa_review: LLMResponseError: Failed to parse",
        }

        result = route_after_qa(state)

        assert result == "error_handler"


class TestReviewPhaseRouting:
    """Tests for routing during review phase."""

    def test_confirm_routes_to_finalize(self):
        """Confirm in review phase routes to finalize."""
        state = {"last_intent": "confirm", "phase": "review"}

        result = route_by_intent(state)

        assert result == "finalize"

    def test_modify_answer_routes_to_element_revision(self):
        """Modify answer in review phase routes to element revision."""
        state = {"last_intent": "modify_answer", "phase": "review"}

        result = route_by_intent(state)

        assert result == "handle_element_revision"

    def test_provide_info_routes_to_element_revision(self):
        """Provide info in review phase treated as element feedback."""
        state = {"last_intent": "provide_information", "phase": "review"}

        result = route_by_intent(state)

        assert result == "handle_element_revision"

    def test_question_routes_to_answer(self):
        """Question in review phase still routes to answer_question."""
        state = {"last_intent": "ask_question", "phase": "review"}

        result = route_by_intent(state)

        assert result == "answer_question"

    def test_unrecognized_routes_to_reprompt(self):
        """Unrecognized intent in review generates clarification."""
        state = {"last_intent": "unrecognized", "phase": "review"}

        result = route_by_intent(state)

        assert result == "reprompt"


class TestRouteAfterFinalize:
    """Tests for route_after_finalize function."""

    def test_complete_phase_routes_to_user_input(self):
        """When phase is complete, route to user_input for export selection."""
        from src.nodes.routing import route_after_finalize

        state = {"phase": "complete"}

        result = route_after_finalize(state)

        assert result == "user_input"

    def test_review_phase_routes_to_user_input(self):
        """When still in review phase, route to user_input."""
        from src.nodes.routing import route_after_finalize

        state = {"phase": "review"}

        result = route_after_finalize(state)

        assert result == "user_input"

    def test_other_phase_routes_to_user_input(self):
        """Other phases route to user_input."""
        from src.nodes.routing import route_after_finalize

        state = {"phase": "drafting"}

        result = route_after_finalize(state)

        assert result == "user_input"


class TestRouteAfterElementRevision:
    """Tests for route_after_element_revision function."""

    def test_routes_to_generate_when_element_set(self):
        """Should route to generate_element when element identified."""
        from src.nodes.routing import route_after_element_revision

        state = {
            "current_element_name": "introduction",
            "phase": "drafting",
        }

        result = route_after_element_revision(state)

        assert result == "generate_element"

    def test_routes_to_user_input_when_no_element(self):
        """Should route to user_input when element not identified."""
        from src.nodes.routing import route_after_element_revision

        state = {
            "current_element_name": None,
            "phase": "review",
        }

        result = route_after_element_revision(state)

        assert result == "user_input"

    def test_routes_to_user_input_when_wrong_phase(self):
        """Should route to user_input when not in drafting phase."""
        from src.nodes.routing import route_after_element_revision

        state = {
            "current_element_name": "introduction",
            "phase": "review",  # Not drafting
        }

        result = route_after_element_revision(state)

        assert result == "user_input"


class TestRouteAfterAdvanceElementReview:
    """Tests for route_after_advance_element with review phase."""

    def test_review_phase_routes_to_finalize(self):
        """When all elements done and in review, route to finalize."""
        state = {"phase": "review"}

        result = route_after_advance_element(state)

        assert result == "finalize"

    def test_drafting_phase_continues_to_generate(self):
        """When still drafting, route to generate_element."""
        state = {"phase": "drafting"}

        result = route_after_advance_element(state)

        assert result == "generate_element"

    def test_drafted_element_routes_to_qa_review(self):
        """Already-drafted elements should go to QA, not be regenerated."""
        from src.models.draft import DraftElement
        elem = DraftElement(name="major_duties", display_name="Major Duties")
        elem.update_content("Some drafted content")
        assert elem.status == "drafted"

        state = {
            "phase": "drafting",
            "current_element_index": 0,
            "draft_elements": [elem.model_dump()],
        }

        result = route_after_advance_element(state)

        assert result == "qa_review"

    def test_complete_phase_routes_to_end(self):
        """When complete, route to end_conversation."""
        state = {"phase": "complete"}

        result = route_after_advance_element(state)

        assert result == "end_conversation"


class TestCompletePhaseRouting:
    """Tests for routing during complete phase (write another flow)."""

    def test_confirm_routes_to_handle_write_another(self):
        """Confirm in complete phase routes to handle_write_another."""
        state = {"last_intent": "confirm", "phase": "complete"}

        result = route_by_intent(state)

        assert result == "handle_write_another"

    def test_reject_routes_to_handle_write_another(self):
        """Reject in complete phase routes to handle_write_another."""
        state = {"last_intent": "reject", "phase": "complete"}

        result = route_by_intent(state)

        assert result == "handle_write_another"

    def test_ask_question_routes_to_answer(self):
        """Question in complete phase still routes to answer_question."""
        state = {"last_intent": "ask_question", "phase": "complete"}

        result = route_by_intent(state)

        assert result == "answer_question"

    def test_unknown_intent_routes_to_reprompt(self):
        """Unknown intents in complete phase generate clarification."""
        state = {"last_intent": "provide_information", "phase": "complete"}

        result = route_by_intent(state)

        assert result == "reprompt"


class TestRouteAfterEndConversation:
    """Tests for route_after_end_conversation function."""

    def test_wants_another_true_routes_to_init(self):
        """When user wants another PD, route to init."""
        from src.nodes.routing import route_after_end_conversation

        state = {"wants_another": True}

        result = route_after_end_conversation(state)

        assert result == "init"

    def test_wants_another_false_routes_to_end(self):
        """When user doesn't want another PD, route to __end__."""
        from src.nodes.routing import route_after_end_conversation

        state = {"wants_another": False}

        result = route_after_end_conversation(state)

        assert result == "__end__"

    def test_wants_another_none_routes_to_user_input(self):
        """When wants_another not set, route to user_input to ask."""
        from src.nodes.routing import route_after_end_conversation

        state = {"wants_another": None}

        result = route_after_end_conversation(state)

        assert result == "user_input"

    def test_wants_another_missing_routes_to_user_input(self):
        """When wants_another not in state, route to user_input."""
        from src.nodes.routing import route_after_end_conversation

        state = {}

        result = route_after_end_conversation(state)

        assert result == "user_input"


class TestRouteAfterExport:
    """Tests for route_after_export function."""

    def test_routes_to_end_conversation_on_success(self):
        """Routes to end_conversation on successful export (no error)."""
        from src.nodes.routing import route_after_export

        state = {"phase": "complete"}  # No last_error = success

        result = route_after_export(state)

        assert result == "end_conversation"

    def test_routes_to_user_input_on_error(self):
        """Routes to user_input when there's an export error."""
        from src.nodes.routing import route_after_export

        state = {"phase": "complete", "last_error": "Export failed"}

        result = route_after_export(state)

        assert result == "user_input"


class TestCompletePhaseExportRouting:
    """Tests for request_export routing during complete phase."""

    def test_request_export_routes_to_export_document(self):
        """request_export in complete phase routes to export_document."""
        state = {"last_intent": "request_export", "phase": "complete"}

        result = route_by_intent(state)

        assert result == "export_document"
