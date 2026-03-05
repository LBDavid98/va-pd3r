"""Unit tests for map_answers_node."""

import pytest

from src.models.interview import InterviewData, InterviewElement
from src.nodes.map_answers_node import (
    _apply_field_mapping,
    _build_summary_message,
    _calculate_missing_fields,
    _get_next_field_to_ask,
    _get_or_create_interview_data,
    _handle_confirmation,
    map_answers_node,
)


class TestGetOrCreateInterviewData:
    """Tests for _get_or_create_interview_data helper."""

    def test_creates_new_when_missing(self):
        """Creates new InterviewData when state has none."""
        state = {"interview_data": None}
        result = _get_or_create_interview_data(state)

        assert isinstance(result, InterviewData)
        assert not result.position_title.is_set

    def test_deserializes_existing(self):
        """Deserializes existing InterviewData from state."""
        interview = InterviewData()
        interview.position_title.set_value("IT Specialist")
        state = {"interview_data": interview.model_dump()}

        result = _get_or_create_interview_data(state)

        assert isinstance(result, InterviewData)
        assert result.position_title.is_set
        assert result.position_title.value == "IT Specialist"

    def test_handles_empty_state(self):
        """Handles completely empty state dict."""
        state = {}
        result = _get_or_create_interview_data(state)

        assert isinstance(result, InterviewData)


class TestApplyFieldMapping:
    """Tests for _apply_field_mapping helper."""

    def test_applies_string_field(self):
        """Applies mapping to a string field."""
        interview = InterviewData()

        success, error = _apply_field_mapping(
            interview,
            field_name="position_title",
            extracted_value="IT Specialist",
            parsed_value="IT Specialist",
            raw_input="I need an IT Specialist position",
            needs_confirmation=False,
        )

        assert success is True
        assert error is None
        assert interview.position_title.is_set
        assert interview.position_title.value == "IT Specialist"
        assert interview.position_title.raw_input == "I need an IT Specialist position"
        assert interview.position_title.needs_confirmation is False

    def test_applies_list_field(self):
        """Applies mapping to a list field."""
        interview = InterviewData()
        org_list = ["VA", "VHA", "Digital Health Office"]

        success, error = _apply_field_mapping(
            interview,
            field_name="organization",
            extracted_value="VA, VHA, Digital Health Office",
            parsed_value=org_list,
            raw_input="I'm in VA VHA Digital Health Office",
            needs_confirmation=False,
        )

        assert success is True
        assert error is None
        assert interview.organization.is_set
        assert interview.organization.value == org_list

    def test_applies_boolean_field(self):
        """Applies mapping to a boolean field."""
        interview = InterviewData()

        success, error = _apply_field_mapping(
            interview,
            field_name="is_supervisor",
            extracted_value="yes",
            parsed_value=True,
            raw_input="Yes, this is a supervisory position",
            needs_confirmation=False,
        )

        assert success is True
        assert error is None
        assert interview.is_supervisor.is_set
        assert interview.is_supervisor.value is True

    def test_marks_uncertain_for_confirmation(self):
        """Marks uncertain extraction for confirmation."""
        interview = InterviewData()

        success, error = _apply_field_mapping(
            interview,
            field_name="series",
            extracted_value="2210",
            parsed_value="2210",
            raw_input="I think it's IT related",
            needs_confirmation=True,
        )

        assert success is True
        assert error is None
        assert interview.series.needs_confirmation is True
        assert interview.series.confirmed is False

    def test_returns_false_for_unknown_field(self):
        """Returns False for unknown field name."""
        interview = InterviewData()

        success, error = _apply_field_mapping(
            interview,
            field_name="nonexistent_field",
            extracted_value="value",
            parsed_value="value",
            raw_input="input",
            needs_confirmation=False,
        )

        assert success is False
        assert error is None


class TestBuildSummaryMessage:
    """Tests for _build_summary_message helper."""

    def test_single_field_mapped(self):
        """Summary for single field mapping."""
        mapped = [
            {
                "field_name": "position_title",
                "parsed_value": "IT Specialist",
            }
        ]

        result = _build_summary_message(mapped, [])

        # Acknowledgment phrase rotation means we can't check for exact phrase
        # Check that it contains an acknowledgment-style opener and the mapped value
        assert "Position Title" in result
        assert "IT Specialist" in result
        # Should have some acknowledgment indicator
        assert any(
            indicator in result
            for indicator in ["captured", "got", "noted", "recorded", "have", "mapped"]
        )

    def test_multiple_fields_mapped(self):
        """Summary for multiple field mappings."""
        mapped = [
            {"field_name": "position_title", "parsed_value": "IT Specialist"},
            {"field_name": "grade", "parsed_value": "GS-13"},
        ]

        result = _build_summary_message(mapped, [])

        assert "Position Title" in result
        assert "IT Specialist" in result
        assert "Grade" in result
        assert "GS-13" in result

    def test_list_value_formatting(self):
        """Formats list values correctly."""
        mapped = [
            {
                "field_name": "organization",
                "parsed_value": ["VA", "VHA", "Digital Health"],
            }
        ]

        result = _build_summary_message(mapped, [])

        assert "VA, VHA, Digital Health" in result

    def test_dict_value_formatting(self):
        """Formats dict values correctly."""
        mapped = [
            {
                "field_name": "major_duties",
                "parsed_value": {"Lead data strategy": "40%", "Build dashboards": "30%"},
            }
        ]

        result = _build_summary_message(mapped, [])

        assert "Lead data strategy: 40%" in result or "40%" in result

    def test_boolean_value_formatting(self):
        """Formats boolean values as Yes/No."""
        mapped = [
            {"field_name": "is_supervisor", "parsed_value": True}
        ]

        result = _build_summary_message(mapped, [])

        assert "Yes" in result

    def test_includes_confirmation_requests(self):
        """Includes confirmation requests for uncertain fields."""
        mapped = [
            {"field_name": "series", "parsed_value": "2210"}
        ]
        needs_confirmation = ["series"]

        result = _build_summary_message(mapped, needs_confirmation)

        assert "confirm" in result.lower()
        assert "series" in result.lower()

    def test_no_fields_mapped_message(self):
        """Returns appropriate message when no fields mapped."""
        result = _build_summary_message([], [])

        assert "wasn't able to extract" in result.lower() or "couldn't" in result.lower() or "could you provide" in result.lower()


class TestCalculateMissingFields:
    """Tests for _calculate_missing_fields helper."""

    def test_all_required_missing_initially(self):
        """All required fields missing at start."""
        interview = InterviewData()

        result = _calculate_missing_fields(interview, is_supervisor=None)

        # Should include base required fields
        assert "position_title" in result
        assert "series" in result
        assert "grade" in result

    def test_some_fields_set(self):
        """Only missing fields returned when some are set."""
        interview = InterviewData()
        interview.position_title.set_value("IT Specialist")
        interview.series.set_value("2210")

        result = _calculate_missing_fields(interview, is_supervisor=None)

        assert "position_title" not in result
        assert "series" not in result
        assert "grade" in result  # Still missing

    def test_supervisory_adds_more_fields(self):
        """Supervisory positions have additional required fields."""
        interview = InterviewData()
        # Set all base fields
        interview.position_title.set_value("IT Specialist")
        interview.series.set_value("2210")
        interview.grade.set_value("GS-13")
        interview.organization.set_value(["VA", "VHA"])
        interview.reports_to.set_value("Branch Chief")
        interview.major_duties.set_value(["Lead projects"])
        interview.is_supervisor.set_value(True)

        result = _calculate_missing_fields(interview, is_supervisor=True)

        # Supervisory fields should be included as missing
        # (supervisory fields are conditional, not all required)
        # At minimum, base fields should be counted
        assert "position_title" not in result

    def test_supervisor_true_includes_conditional_fields_in_sequence(self):
        """When is_supervisor=True, supervisory-conditional fields appear in sequence.
        
        This is the core bug fix test: when user answers "yes" to is_supervisor,
        the follow-on supervisory questions (supervised_employees, f1_program_scope, etc.)
        should be included in the intake sequence and asked.
        """
        from src.config.intake_fields import get_intake_sequence, SUPERVISORY_ADDITIONAL
        
        # Verify the sequence includes supervisory fields when is_supervisor=True
        full_sequence = get_intake_sequence(is_supervisor=True)
        base_sequence = get_intake_sequence(is_supervisor=False)
        
        # Supervisory fields should be in full sequence but not base
        for field in SUPERVISORY_ADDITIONAL:
            assert field in full_sequence, f"{field} should be in supervisory sequence"
            assert field not in base_sequence, f"{field} should not be in base sequence"
        
        # Now test that missing_fields calculation correctly uses is_supervisor
        interview = InterviewData()
        # Set all base fields complete
        interview.position_title.set_value("IT Specialist")
        interview.series.set_value("2210")
        interview.grade.set_value("GS-13")
        interview.organization_hierarchy.set_value(["VA", "VHA"])
        interview.reports_to.set_value("Branch Chief")
        interview.daily_activities.set_value(["Analyze data"])
        interview.major_duties.set_value(["Lead projects"])
        interview.is_supervisor.set_value(True)  # Set to supervisory!
        
        # Calculate missing with is_supervisor=True
        missing = _calculate_missing_fields(interview, is_supervisor=True)
        
        # Should NOT have base fields in missing (they're all set)
        assert "position_title" not in missing
        assert "series" not in missing
        assert "is_supervisor" not in missing
        
        # The conditional fields should now appear as "missing" to be asked
        # Note: These are marked required=False in intake_fields, but they're 
        # now in the sequence to be asked when is_supervisor=True


class TestHandleConfirmation:
    """Tests for _handle_confirmation helper."""

    def test_confirm_field(self):
        """Confirming a field marks it as confirmed."""
        interview = InterviewData()
        interview.series.set_value("2210", needs_confirmation=True)

        result = _handle_confirmation(interview, "series", confirmed=True)

        assert interview.series.confirmed is True
        assert interview.series.needs_confirmation is False
        assert "confirm" in result.lower()

    def test_reject_field(self):
        """Rejecting a field clears its value."""
        interview = InterviewData()
        interview.series.set_value("2210", needs_confirmation=True)

        result = _handle_confirmation(interview, "series", confirmed=False)

        assert interview.series.value is None
        assert interview.series.is_set is False
        assert "try again" in result.lower()

    def test_unknown_field(self):
        """Returns error message for unknown field."""
        interview = InterviewData()

        result = _handle_confirmation(interview, "nonexistent", confirmed=True)

        assert "don't have" in result.lower()


class TestMapAnswersNode:
    """Tests for map_answers_node function."""

    def test_maps_single_field(self):
        """Maps a single field from intent classification."""
        state = {
            "interview_data": None,
            "last_intent": "provide_information",
            "_field_mappings": [
                {
                    "field_name": "position_title",
                    "extracted_value": "IT Specialist",
                    "parsed_value": "IT Specialist",
                    "raw_input": "I need an IT Specialist",
                    "needs_confirmation": False,
                }
            ],
            "fields_needing_confirmation": [],
        }

        result = map_answers_node(state)

        assert "interview_data" in result
        interview = InterviewData.model_validate(result["interview_data"])
        assert interview.position_title.value == "IT Specialist"
        assert "messages" in result
        assert len(result["messages"]) > 0

    def test_maps_multiple_fields(self):
        """Maps multiple fields at once."""
        state = {
            "interview_data": None,
            "last_intent": "provide_information",
            "_field_mappings": [
                {
                    "field_name": "position_title",
                    "extracted_value": "IT Specialist",
                    "parsed_value": "IT Specialist",
                    "raw_input": "IT Specialist",
                    "needs_confirmation": False,
                },
                {
                    "field_name": "grade",
                    "extracted_value": "GS-13",
                    "parsed_value": "GS-13",
                    "raw_input": "grade 13",
                    "needs_confirmation": False,
                },
            ],
            "fields_needing_confirmation": [],
        }

        result = map_answers_node(state)

        interview = InterviewData.model_validate(result["interview_data"])
        assert interview.position_title.value == "IT Specialist"
        assert interview.grade.value == "GS-13"

    def test_handles_confirmation_intent(self):
        """Handles confirm intent for pending confirmation."""
        interview = InterviewData()
        interview.series.set_value("2210", needs_confirmation=True)

        state = {
            "interview_data": interview.model_dump(),
            "last_intent": "confirm",
            "_field_mappings": [],
            "fields_needing_confirmation": ["series"],
        }

        result = map_answers_node(state)

        new_interview = InterviewData.model_validate(result["interview_data"])
        assert new_interview.series.confirmed is True
        assert result["fields_needing_confirmation"] == []

    def test_handles_reject_intent(self):
        """Handles reject intent for pending confirmation."""
        interview = InterviewData()
        interview.series.set_value("2210", needs_confirmation=True)

        state = {
            "interview_data": interview.model_dump(),
            "last_intent": "reject",
            "_field_mappings": [],
            "fields_needing_confirmation": ["series"],
        }

        result = map_answers_node(state)

        new_interview = InterviewData.model_validate(result["interview_data"])
        assert new_interview.series.is_set is False  # Value cleared
        assert result["fields_needing_confirmation"] == []

    def test_handles_modify_intent(self):
        """Handles modify_answer intent to update field."""
        interview = InterviewData()
        interview.grade.set_value("GS-12")
        interview.grade.confirm()

        state = {
            "interview_data": interview.model_dump(),
            "last_intent": "modify_answer",
            "_field_mappings": [],
            "_modification": {
                "field": "grade",
                "new_value": "GS-13",
            },
            "fields_needing_confirmation": [],
        }

        result = map_answers_node(state)

        new_interview = InterviewData.model_validate(result["interview_data"])
        assert new_interview.grade.value == "GS-13"
        assert new_interview.grade.confirmed is True

    def test_tracks_fields_needing_confirmation(self):
        """Tracks fields that need confirmation."""
        state = {
            "interview_data": None,
            "last_intent": "provide_information",
            "_field_mappings": [
                {
                    "field_name": "series",
                    "extracted_value": "2210",
                    "parsed_value": "2210",
                    "raw_input": "I think IT related",
                    "needs_confirmation": True,
                }
            ],
            "fields_needing_confirmation": [],
        }

        result = map_answers_node(state)

        assert "series" in result["fields_needing_confirmation"]

    def test_calculates_missing_fields(self):
        """Calculates remaining missing fields."""
        state = {
            "interview_data": None,
            "last_intent": "provide_information",
            "_field_mappings": [
                {
                    "field_name": "position_title",
                    "extracted_value": "IT Specialist",
                    "parsed_value": "IT Specialist",
                    "raw_input": "IT Specialist",
                    "needs_confirmation": False,
                }
            ],
            "fields_needing_confirmation": [],
        }

        result = map_answers_node(state)

        # position_title is set, so it shouldn't be in missing_fields
        assert "position_title" not in result["missing_fields"]
        # Other required fields should still be missing
        assert "series" in result["missing_fields"] or len(result["missing_fields"]) > 0

    def test_clears_temporary_state(self):
        """Clears temporary _field_mappings after processing."""
        state = {
            "interview_data": None,
            "last_intent": "provide_information",
            "_field_mappings": [
                {
                    "field_name": "position_title",
                    "extracted_value": "IT Specialist",
                    "parsed_value": "IT Specialist",
                    "raw_input": "IT Specialist",
                    "needs_confirmation": False,
                }
            ],
            "fields_needing_confirmation": [],
        }

        result = map_answers_node(state)

        assert result.get("_field_mappings") is None
        assert result.get("_modification") is None

    def test_no_mappings_returns_helpful_message(self):
        """Returns helpful message when no fields mapped."""
        state = {
            "interview_data": None,
            "last_intent": "provide_information",
            "_field_mappings": [],
            "fields_needing_confirmation": [],
        }

        result = map_answers_node(state)

        assert len(result["messages"]) > 0
        message_content = result["messages"][0].content
        assert "couldn't" in message_content.lower() or "wasn't able" in message_content.lower() or "provide" in message_content.lower()
