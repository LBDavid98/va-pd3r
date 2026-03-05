"""Unit tests for prepare_next_node."""

import pytest

from src.models.interview import InterviewData
from src.nodes.prepare_next_node import (
    _build_confirmation_prompt,
    _format_interview_summary,
    _get_field_prompt,
    _get_next_field_in_sequence,
    prepare_next_node,
)


class TestGetFieldPrompt:
    """Tests for _get_field_prompt helper."""

    def test_known_field_returns_guidance(self):
        """Returns user_guidance for known fields."""
        result = _get_field_prompt("position_title")
        assert len(result) > 0
        # Should be the user_guidance, not the raw prompt
        assert "title" in result.lower()

    def test_unknown_field_returns_generic(self):
        """Returns generic prompt for unknown fields."""
        result = _get_field_prompt("nonexistent_field")
        assert "nonexistent field" in result.lower()


class TestBuildConfirmationPrompt:
    """Tests for _build_confirmation_prompt helper."""

    def test_string_value(self):
        """Builds prompt for string value."""
        result = _build_confirmation_prompt("grade", "GS-13")

        assert "grade" in result.lower()
        assert "GS-13" in result
        assert "correct" in result.lower()

    def test_list_value(self):
        """Builds prompt for list value."""
        result = _build_confirmation_prompt("organization", ["VA", "VHA"])

        assert "organization" in result.lower()
        assert "VA, VHA" in result

    def test_boolean_value_true(self):
        """Builds prompt for True boolean value."""
        result = _build_confirmation_prompt("is_supervisor", True)

        assert "supervisor" in result.lower()
        assert "Yes" in result

    def test_boolean_value_false(self):
        """Builds prompt for False boolean value."""
        result = _build_confirmation_prompt("is_supervisor", False)

        assert "No" in result

    def test_dict_value(self):
        """Builds prompt for dict value."""
        result = _build_confirmation_prompt(
            "major_duties",
            {"Lead projects": "40%", "Analyze data": "30%"}
        )

        assert "major duties" in result.lower()
        assert "40%" in result or "Lead projects" in result


class TestGetNextFieldInSequence:
    """Tests for _get_next_field_in_sequence helper."""

    def test_returns_first_missing_in_sequence(self):
        """Returns first missing field according to sequence."""
        missing = ["grade", "position_title", "series"]
        result = _get_next_field_in_sequence(missing, is_supervisor=None)

        # position_title comes first in sequence
        assert result == "position_title"

    def test_returns_none_when_all_complete(self):
        """Returns None when no missing fields."""
        result = _get_next_field_in_sequence([], is_supervisor=None)
        assert result is None

    def test_includes_supervisory_fields_when_supervisor(self):
        """Includes supervisory fields when is_supervisor=True."""
        missing = ["supervised_employees"]
        result = _get_next_field_in_sequence(missing, is_supervisor=True)

        assert result == "supervised_employees"


class TestPrepareNextNode:
    """Tests for prepare_next_node function."""

    def test_asks_for_confirmation_first(self):
        """Asks for confirmation when fields need confirmation."""
        interview = InterviewData()
        interview.series.set_value("2210", needs_confirmation=True)

        state = {
            "interview_data": interview.model_dump(),
            "fields_needing_confirmation": ["series"],
            "missing_fields": ["grade"],
        }

        result = prepare_next_node(state)

        assert result["current_field"] == "series"
        assert "2210" in result["messages"][0].content
        assert "correct" in result["messages"][0].content.lower()

    def test_asks_for_next_missing_field(self):
        """Asks for next missing field when no confirmations pending."""
        interview = InterviewData()

        state = {
            "interview_data": interview.model_dump(),
            "fields_needing_confirmation": [],
            "missing_fields": ["position_title", "series"],
        }

        result = prepare_next_node(state)

        assert result["current_field"] == "position_title"
        assert "title" in result["messages"][0].content.lower()

    def test_signals_completion_when_done(self):
        """Transitions to requirements phase and shows summary when no fields missing."""
        interview = InterviewData()
        interview.position_title.set_value("IT Specialist")
        interview.position_title.confirm()

        state = {
            "interview_data": interview.model_dump(),
            "fields_needing_confirmation": [],
            "missing_fields": [],
        }

        result = prepare_next_node(state)

        assert result["current_field"] is None
        assert result["phase"] == "requirements"  # Now transitions directly
        # Should show the summary with "Interview Complete" and collected data
        content = result["messages"][0].content.lower()
        assert "complete" in content or "everything" in content
        assert "it specialist" in content  # Shows the collected position title

    def test_returns_message_for_next_prompt(self):
        """Returns message object for display."""
        state = {
            "interview_data": None,
            "fields_needing_confirmation": [],
            "missing_fields": ["position_title"],
        }

        result = prepare_next_node(state)

        assert "messages" in result
        assert len(result["messages"]) > 0
        assert result["next_prompt"] == result["messages"][0].content


class TestPrepareNextNodeRequirementsPhase:
    """Tests for prepare_next_node in the requirements phase.
    
    The requirements phase is reached when the interview is complete.
    prepare_next_node should display the interview summary and ask
    for user confirmation before FES evaluation begins.
    """

    def test_shows_summary_in_requirements_phase(self):
        """Shows interview summary when phase is requirements."""
        interview = InterviewData()
        interview.position_title.set_value("IT Specialist")
        interview.position_title.confirm()
        interview.series.set_value("2210")
        interview.series.confirm()
        interview.grade.set_value("GS-13")
        interview.grade.confirm()

        state = {
            "phase": "requirements",
            "interview_data": interview.model_dump(),
            "fields_needing_confirmation": [],
            "missing_fields": [],
        }

        result = prepare_next_node(state)

        # Should include the collected data in summary
        content = result["messages"][0].content
        assert "IT Specialist" in content
        assert "2210" in content
        assert "GS-13" in content

    def test_asks_for_confirmation_in_requirements_phase(self):
        """Asks 'Does this look correct?' in requirements phase."""
        interview = InterviewData()
        interview.position_title.set_value("IT Specialist")

        state = {
            "phase": "requirements",
            "interview_data": interview.model_dump(),
            "fields_needing_confirmation": [],
            "missing_fields": [],
        }

        result = prepare_next_node(state)

        content = result["messages"][0].content.lower()
        # Should ask for confirmation
        assert "look correct" in content or "yes" in content
        # Should explain what happens next
        assert "position description" in content or "start" in content

    def test_clears_current_field_in_requirements_phase(self):
        """Sets current_field to None in requirements phase."""
        interview = InterviewData()
        interview.position_title.set_value("IT Specialist")

        state = {
            "phase": "requirements",
            "interview_data": interview.model_dump(),
            "fields_needing_confirmation": [],
            "missing_fields": [],
        }

        result = prepare_next_node(state)

        assert result["current_field"] is None

    def test_shows_category_headers_in_summary(self):
        """Summary includes category headers for organization."""
        interview = InterviewData()
        interview.position_title.set_value("IT Specialist")
        interview.series.set_value("2210")
        interview.organization.set_value(["VA", "VHA"])

        state = {
            "phase": "requirements",
            "interview_data": interview.model_dump(),
        }

        result = prepare_next_node(state)

        content = result["messages"][0].content
        # Should have markdown bold headers
        assert "**" in content
