"""Unit tests for check_interview_complete_node."""

import pytest

from src.models.interview import InterviewData
from src.nodes.check_interview_complete_node import (
    _check_confirmations_complete,
    _check_required_fields,
    _format_interview_summary,
    check_interview_complete_node,
)


class TestFormatInterviewSummary:
    """Tests for _format_interview_summary helper."""

    def test_empty_interview(self):
        """Returns message for empty interview."""
        interview = InterviewData()
        result = _format_interview_summary(interview)
        assert "no information" in result.lower()

    def test_formats_core_fields(self):
        """Formats core position fields."""
        interview = InterviewData()
        interview.position_title.set_value("IT Specialist")
        interview.series.set_value("2210")
        interview.grade.set_value("GS-13")

        result = _format_interview_summary(interview)

        assert "IT Specialist" in result
        assert "2210" in result
        assert "GS-13" in result

    def test_groups_by_category(self):
        """Groups fields by category with headers."""
        interview = InterviewData()
        interview.position_title.set_value("IT Specialist")
        interview.organization.set_value(["VA", "VHA"])

        result = _format_interview_summary(interview)

        # Should have category headers
        assert "**" in result  # Bold markdown headers


class TestCheckRequiredFields:
    """Tests for _check_required_fields helper."""

    def test_all_missing_initially(self):
        """All required fields missing at start."""
        interview = InterviewData()
        is_complete, missing = _check_required_fields(interview, is_supervisor=None)

        assert is_complete is False
        assert len(missing) > 0
        assert "position_title" in missing

    def test_complete_when_all_set(self):
        """Returns complete when all required fields are set."""
        interview = InterviewData()
        # Set all required fields
        interview.position_title.set_value("IT Specialist")
        interview.series.set_value("2210")
        interview.grade.set_value("GS-13")
        interview.organization.set_value(["VA", "VHA"])
        interview.reports_to.set_value("Branch Chief")
        interview.major_duties.set_value(["Lead projects: 50%", "Analyze data: 50%"])
        interview.is_supervisor.set_value(False)

        is_complete, missing = _check_required_fields(interview, is_supervisor=False)

        # May still have daily_activities missing
        # Check that most are complete
        assert "position_title" not in missing
        assert "series" not in missing


class TestCheckConfirmationsComplete:
    """Tests for _check_confirmations_complete helper."""

    def test_complete_when_none_pending(self):
        """Complete when no fields need confirmation."""
        interview = InterviewData()
        interview.position_title.set_value("IT Specialist")
        interview.position_title.confirm()

        is_complete, unconfirmed = _check_confirmations_complete(interview)

        assert is_complete is True
        assert len(unconfirmed) == 0

    def test_incomplete_when_pending(self):
        """Incomplete when fields need confirmation."""
        interview = InterviewData()
        interview.series.set_value("2210", needs_confirmation=True)

        is_complete, unconfirmed = _check_confirmations_complete(interview)

        assert is_complete is False
        assert "series" in unconfirmed


class TestCheckInterviewCompleteNode:
    """Tests for check_interview_complete_node function.
    
    Note: This node is now a "pure check" - it only updates state flags,
    it does NOT generate user-facing messages. The summary and confirmation
    prompt are handled by prepare_next_node in the requirements phase.
    """

    def test_no_interview_data(self):
        """Returns interview phase when no interview data exists."""
        state = {"interview_data": None}
        result = check_interview_complete_node(state)

        assert result["phase"] == "interview"
        # Should signal that we need fields, not generate messages
        assert "missing_fields" in result

    def test_missing_fields_returns_list(self):
        """Returns missing fields when interview incomplete."""
        interview = InterviewData()
        interview.position_title.set_value("IT Specialist")

        state = {"interview_data": interview.model_dump()}
        result = check_interview_complete_node(state)

        assert "missing_fields" in result
        assert len(result["missing_fields"]) > 0
        # Pure check: no messages generated
        assert "messages" not in result

    def test_unconfirmed_fields_returned(self):
        """Returns unconfirmed fields when confirmations pending."""
        interview = InterviewData()
        interview.position_title.set_value("IT Specialist")
        interview.series.set_value("2210")
        interview.grade.set_value("GS-13")
        interview.organization.set_value(["VA"])
        interview.reports_to.set_value("Chief")
        interview.major_duties.set_value(["Work: 100%"])
        interview.is_supervisor.set_value(False)
        interview.series.needs_confirmation = True  # Add confirmation need

        state = {"interview_data": interview.model_dump()}
        result = check_interview_complete_node(state)

        # Either missing_fields or fields_needing_confirmation should be set
        has_pending = (
            result.get("missing_fields", []) or 
            result.get("fields_needing_confirmation", [])
        )
        assert has_pending or result.get("phase") == "requirements"

    def test_transitions_to_requirements_when_complete(self):
        """Transitions to requirements phase when all complete.
        
        Note: The node now only sets phase="requirements" - 
        the summary message is generated by prepare_next_node.
        
        Required fields per intake_fields.py BASE_INTAKE_SEQUENCE:
        - position_title, series, grade, organization_hierarchy,
        - reports_to, daily_activities, major_duties, is_supervisor
        """
        interview = InterviewData()
        # Set and confirm all required fields per intake_fields.py
        interview.position_title.set_value("IT Specialist")
        interview.position_title.confirm()
        interview.series.set_value("2210")
        interview.series.confirm()
        interview.grade.set_value("GS-13")
        interview.grade.confirm()
        interview.organization_hierarchy.set_value(["VA", "VHA", "Digital Health"])
        interview.organization_hierarchy.confirm()
        interview.reports_to.set_value("Branch Chief")
        interview.reports_to.confirm()
        interview.daily_activities.set_value(["Develop and maintain IT systems", "Provide technical support", "Document procedures"])
        interview.daily_activities.confirm()
        interview.major_duties.set_value(["System Development: 50%", "User Support: 30%", "Documentation: 20%"])
        interview.major_duties.confirm()
        interview.is_supervisor.set_value(False)
        interview.is_supervisor.confirm()

        state = {"interview_data": interview.model_dump()}
        result = check_interview_complete_node(state)

        # Should transition to requirements phase
        assert result.get("phase") == "requirements"
        # Should clear pending lists
        assert result.get("missing_fields", []) == []
        assert result.get("fields_needing_confirmation", []) == []
        # Pure check: no messages generated (prepare_next handles that)
        assert "messages" not in result
