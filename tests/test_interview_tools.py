"""Tests for interview tools and LLM-driven tool selection.

These tests verify that:
1. Interview tools work correctly in isolation
2. The interview agent selects appropriate tools based on user input
3. State-aware prompts render correctly
"""

import pytest
from unittest.mock import MagicMock, patch

from src.tools.interview_tools import (
    INTERVIEW_TOOLS,
    save_field_answer,
    confirm_field_value,
    answer_user_question,
    check_interview_complete,
    request_field_clarification,
    modify_field_value,
    get_next_required_field,
    get_field_context,
    get_interview_progress,
)
from src.models.interview import InterviewData
from src.agents.interview_agent import build_interview_prompt
from src.config.intake_fields import BASE_INTAKE_SEQUENCE


class TestInterviewToolsBasic:
    """Test basic tool functionality."""

    def test_save_field_answer_valid_field(self):
        """Test saving a valid field answer."""
        result = save_field_answer.invoke({
            "field_name": "position_title",
            "value": "Data Scientist",
            "raw_input": "The position is Data Scientist",
        })
        assert "Saved position_title" in result
        assert "Data Scientist" in result

    def test_save_field_answer_invalid_field(self):
        """Test error handling for invalid field name."""
        result = save_field_answer.invoke({
            "field_name": "invalid_field",
            "value": "test",
            "raw_input": "test input",
        })
        assert "Error" in result
        assert "Unknown field" in result

    def test_save_field_answer_boolean_coercion(self):
        """Test boolean field type coercion."""
        result = save_field_answer.invoke({
            "field_name": "is_supervisor",
            "value": "yes",
            "raw_input": "Yes, this position supervises others",
        })
        assert "Saved is_supervisor" in result

    def test_save_field_answer_with_confirmation(self):
        """Test saving with needs_confirmation flag."""
        result = save_field_answer.invoke({
            "field_name": "grade",
            "value": "13",
            "raw_input": "I think it's around GS-13",
            "needs_confirmation": True,
        })
        assert "needs confirmation" in result

    def test_confirm_field_value_valid(self):
        """Test confirming a valid field."""
        result = confirm_field_value.invoke({"field_name": "position_title"})
        assert "Confirmed" in result

    def test_confirm_field_value_invalid(self):
        """Test error for invalid field name."""
        result = confirm_field_value.invoke({"field_name": "invalid_field"})
        assert "Error" in result

    def test_answer_user_question_process(self):
        """Test answering a process question."""
        result = answer_user_question.invoke({
            "question": "What fields do I need to provide?",
            "is_hr_specific": False,
        })
        # Should return helpful guidance about the interview process
        assert "collecting" in result.lower() or "information" in result.lower()

    def test_answer_user_question_hr_specific(self, skip_without_api_key):
        """Test answering an HR-specific question uses RAG.
        
        This test requires OPENAI_API_KEY since it calls the real RAG system.
        """
        result = answer_user_question.invoke({
            "question": "What is Factor 1 in FES?",
            "is_hr_specific": True,
        })
        # Should return actual RAG results with citations
        assert "Source" in result or "factor" in result.lower()

    def test_request_field_clarification(self):
        """Test requesting field clarification."""
        result = request_field_clarification.invoke({
            "field_name": "major_duties",
            "clarification_request": "Please provide percentages for each duty",
        })
        assert "Clarification needed" in result
        assert "major_duties" in result

    def test_modify_field_value(self):
        """Test modifying a field value."""
        result = modify_field_value.invoke({
            "field_name": "grade",
            "new_value": "14",
            "raw_input": "Actually, make it GS-14",
            "reason": "Changed requirements",
        })
        assert "Modified grade" in result
        assert "14" in result


class TestInterviewProgressHelpers:
    """Test helper functions for interview progress tracking."""

    def test_get_next_required_field_empty(self):
        """Test getting next field with no data collected."""
        interview_data = InterviewData()
        next_field = get_next_required_field(interview_data)
        assert next_field == "position_title"  # First in sequence

    def test_get_next_required_field_partial(self):
        """Test getting next field with some data collected."""
        interview_data = InterviewData()
        interview_data.position_title.set_value("Data Scientist")
        interview_data.series.set_value("1560")
        
        next_field = get_next_required_field(interview_data)
        assert next_field == "grade"  # Third in sequence

    def test_get_next_required_field_needs_confirmation(self):
        """Test that fields needing confirmation are prioritized."""
        interview_data = InterviewData()
        interview_data.position_title.set_value(
            "Data Scientist",
            needs_confirmation=True,
        )
        interview_data.series.set_value("1560")
        
        next_field = get_next_required_field(interview_data)
        # Should return unset field first, then confirmation
        assert next_field == "grade"

    def test_get_next_required_field_complete(self):
        """Test when all fields are complete."""
        interview_data = InterviewData()
        for field_name in BASE_INTAKE_SEQUENCE:
            element = getattr(interview_data, field_name)
            element.set_value("test_value")
        
        next_field = get_next_required_field(interview_data)
        assert next_field is None

    def test_get_field_context_valid(self):
        """Test getting context for a valid field."""
        context = get_field_context("grade")
        assert context["field_name"] == "grade"
        assert "prompt" in context
        assert "field_type" in context
        assert context["field_type"] == "string"

    def test_get_field_context_invalid(self):
        """Test getting context for invalid field returns empty dict."""
        context = get_field_context("nonexistent_field")
        assert context == {}

    def test_get_interview_progress(self):
        """Test getting interview progress summary."""
        interview_data = InterviewData()
        interview_data.position_title.set_value("Data Scientist")
        interview_data.series.set_value("1560", needs_confirmation=True)
        
        progress = get_interview_progress(interview_data)
        
        assert "position_title" in progress["collected_fields"]
        assert "series" in progress["collected_fields"]
        assert "series" in progress["fields_needing_confirmation"]
        assert "grade" in progress["remaining_fields"]
        assert progress["is_complete"] is False


class TestInterviewAgentPrompt:
    """Test state-aware prompt building."""

    def test_build_prompt_with_current_field(self):
        """Test prompt includes current field context."""
        interview_data = InterviewData()
        prompt = build_interview_prompt(interview_data, "position_title")
        
        assert "position_title" in prompt.lower() or "Position Title" in prompt
        assert "Pete" in prompt
        assert "save_field_answer" in prompt

    def test_build_prompt_shows_progress(self):
        """Test prompt shows collected fields."""
        interview_data = InterviewData()
        interview_data.position_title.set_value("Data Scientist")
        
        prompt = build_interview_prompt(interview_data)
        
        assert "position_title" in prompt.lower()
        assert "Data Scientist" in prompt or "Collected" in prompt

    def test_build_prompt_auto_detects_field(self):
        """Test prompt auto-detects next field when not specified."""
        interview_data = InterviewData()
        interview_data.position_title.set_value("Data Scientist")
        interview_data.series.set_value("1560")
        
        prompt = build_interview_prompt(interview_data)
        
        # Should be asking about grade (third field)
        assert "grade" in prompt.lower()

    def test_build_prompt_all_complete(self):
        """Test prompt for when all fields are complete."""
        interview_data = InterviewData()
        for field_name in BASE_INTAKE_SEQUENCE:
            element = getattr(interview_data, field_name)
            element.set_value("test_value")
        
        prompt = build_interview_prompt(interview_data)
        
        assert "All" in prompt or "collected" in prompt.lower()


class TestToolSelection:
    """Test that tools have appropriate descriptions for LLM selection."""

    def test_all_tools_have_descriptions(self):
        """Verify all tools have docstrings for LLM."""
        for tool in INTERVIEW_TOOLS:
            assert tool.description is not None
            assert len(tool.description) > 10

    def test_save_field_answer_description(self):
        """Test save_field_answer has useful description."""
        desc = save_field_answer.description
        assert "save" in desc.lower()
        assert "field" in desc.lower()

    def test_answer_question_description(self):
        """Test answer_user_question has useful description."""
        desc = answer_user_question.description
        assert "question" in desc.lower()

    def test_tool_names_are_descriptive(self):
        """Test tool names are clear and descriptive."""
        tool_names = [t.name for t in INTERVIEW_TOOLS]
        assert "save_field_answer" in tool_names
        assert "confirm_field_value" in tool_names
        assert "answer_user_question" in tool_names


# =============================================================================
# EXPECTED TOOL SELECTION SCENARIOS (Documentation)
# =============================================================================
# These scenarios document expected LLM behavior for common user inputs.
# Real LLM tests live in test_e2e.py and test_integration_rag.py.
#
# Scenario 1: User provides field value
#   User: "The position title is Senior Data Scientist"
#   Expected: save_field_answer(field_name="position_title", value="Senior Data Scientist", ...)
#
# Scenario 2: User asks question
#   User: "What's a job series?"
#   Expected: answer_user_question(question="What's a job series?", is_hr_specific=True)
#
# Scenario 3: User confirms value
#   Context: field_needing_confirmation = ["grade"]
#   User: "Yes, that's correct"
#   Expected: confirm_field_value(field_name="grade")
#
# Scenario 4: User modifies previous value
#   User: "Actually, change the grade to GS-14"
#   Expected: modify_field_value(field_name="grade", new_value="14", ...)
#
# Scenario 5: User provides multiple fields
#   User: "The title is Data Scientist and it's a GS-13"
#   Expected: Two save_field_answer calls
#
# To add real LLM tests for these scenarios, follow the pattern in test_e2e.py
# and mark with @pytest.mark.llm
# =============================================================================
