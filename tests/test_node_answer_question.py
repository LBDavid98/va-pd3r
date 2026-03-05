"""Unit tests for answer_question_node.

NOTE: Tests for _answer_without_llm have been removed per ADR-005 (no-mock-llm).
The answer_question_node ALWAYS requires a real LLM call - there are no fallbacks.
Integration tests that test the full node require ANTHROPIC_API_KEY to be set.
"""

import pytest

from src.models.interview import InterviewData
from src.nodes.answer_question_node import (
    _build_interview_summary,
)


class TestBuildInterviewSummary:
    """Tests for _build_interview_summary helper."""

    def test_empty_state_returns_empty(self):
        """Returns empty string when no interview data."""
        state = {"interview_data": None}
        result = _build_interview_summary(state)
        assert result == ""

    def test_empty_interview_returns_empty(self):
        """Returns empty string when interview has no values."""
        interview = InterviewData()
        state = {"interview_data": interview.model_dump()}
        result = _build_interview_summary(state)
        assert result == ""

    def test_formats_string_fields(self):
        """Formats string fields correctly."""
        interview = InterviewData()
        interview.position_title.set_value("IT Specialist")
        state = {"interview_data": interview.model_dump()}

        result = _build_interview_summary(state)

        assert "Position Title" in result
        assert "IT Specialist" in result

    def test_formats_list_fields(self):
        """Formats list fields as comma-separated."""
        interview = InterviewData()
        interview.organization.set_value(["VA", "VHA", "Digital Health"])
        state = {"interview_data": interview.model_dump()}

        result = _build_interview_summary(state)

        assert "VA, VHA, Digital Health" in result

    def test_formats_boolean_fields(self):
        """Formats boolean fields as Yes/No."""
        interview = InterviewData()
        interview.is_supervisor.set_value(True)
        state = {"interview_data": interview.model_dump()}

        result = _build_interview_summary(state)

        assert "Yes" in result


# =============================================================================
# TestAnswerQuestionNode removed per ADR-005 (no-mock-llm)
# =============================================================================
# The answer_question_node ALWAYS requires real LLM calls.
# These tests attempted to call the node directly without LLM, which:
# 1. Would fail without OPENAI_API_KEY
# 2. Cannot be mocked at the application level per ADR-005
#
# Integration tests for answer_question_node should:
# - Be marked @pytest.mark.llm
# - Run the full graph flow
# - Use real LLM calls
#
# See test_e2e.py for full integration testing patterns.
# =============================================================================
