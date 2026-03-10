"""Tests for finalize node and review phase functionality."""

import os

import pytest

from src.models.draft import DraftElement
from src.models.interview import InterviewData
from src.nodes.finalize_node import (
    check_all_elements_complete,
    finalize_node,
    get_incomplete_elements,
    handle_element_revision_request,
)


# Check if API key is available for LLM tests
OPENAI_AVAILABLE = bool(os.getenv("OPENAI_API_KEY"))
skip_without_llm = pytest.mark.skipif(
    not OPENAI_AVAILABLE,
    reason="OPENAI_API_KEY required - element extraction is LLM-driven (ADR-007)"
)


class TestFinalizeNode:
    """Tests for finalize_node function."""

    def test_returns_to_interview_when_no_elements(self):
        """Should route to interview when no draft elements."""
        state = {
            "draft_elements": [],
            "interview_data": None,
            "last_intent": "",
        }

        result = finalize_node(state)

        assert result["phase"] == "interview"
        assert "No draft elements" in result["messages"][0].content

    def test_shows_review_on_first_call(self):
        """Should show assembled document for review."""
        elements = [
            DraftElement(
                name="introduction",
                display_name="Introduction",
                content="This is the introduction.",
                status="approved",
            ).model_dump(),
            DraftElement(
                name="major_duties",
                display_name="Major Duties",
                content="These are the duties.",
                status="approved",
            ).model_dump(),
        ]

        state = {
            "draft_elements": elements,
            "interview_data": None,
            "last_intent": "",
        }

        result = finalize_node(state)

        content = result["messages"][0].content
        assert "complete position description" in content.lower()
        assert "Introduction" in content
        assert "approve" in content.lower() or "yes" in content.lower()

    def test_confirms_when_user_approves(self):
        """Should prepare for export when user confirms."""
        elements = [
            DraftElement(
                name="introduction",
                display_name="Introduction",
                content="Content",
                status="approved",
            ).model_dump()
        ]

        state = {
            "draft_elements": elements,
            "interview_data": None,
            "last_intent": "confirm",
        }

        result = finalize_node(state)

        assert result["phase"] == "complete"
        content = result["messages"][0].content
        assert "finalized" in content.lower() or "export" in content.lower()


class TestHandleElementRevisionRequest:
    """Tests for handle_element_revision_request function.
    
    NOTE: These tests require OPENAI_API_KEY because element identification
    is now LLM-driven per ADR-007 (no heuristic decision making).
    """

    @skip_without_llm
    async def test_identifies_introduction_from_message(self):
        """Should identify introduction element from user message."""
        elements = [
            DraftElement(
                name="introduction",
                display_name="Introduction",
                content="Original intro",
                status="approved",
            ).model_dump(),
            DraftElement(
                name="major_duties",
                display_name="Major Duties",
                content="Duties content",
                status="approved",
            ).model_dump(),
        ]

        # Create mock message
        from langchain_core.messages import HumanMessage

        state = {
            "draft_elements": elements,
            "messages": [HumanMessage(content="Change the introduction to be more formal")],
        }

        result = await handle_element_revision_request(state)

        assert result["current_element_name"] == "introduction"
        assert result["current_element_index"] == 0
        assert result["phase"] == "drafting"

    @skip_without_llm
    async def test_identifies_factor_from_message(self):
        """Should identify factor elements from user message."""
        elements = [
            DraftElement(
                name="factor_1_knowledge",
                display_name="Factor 1: Knowledge Required",
                content="Factor content",
                status="approved",
            ).model_dump()
        ]

        from langchain_core.messages import HumanMessage

        state = {
            "draft_elements": elements,
            "messages": [HumanMessage(content="Revise factor 1")],
        }

        result = await handle_element_revision_request(state)

        assert result["current_element_name"] == "factor_1_knowledge"
        assert result["current_element_index"] == 0

    @skip_without_llm
    async def test_asks_clarification_when_element_unclear(self):
        """Should ask for clarification when element can't be identified from vague request."""
        # Need multiple elements so "make some changes" is actually ambiguous
        elements = [
            DraftElement(
                name="introduction",
                display_name="Introduction",
                content="Content",
                status="approved",
            ).model_dump(),
            DraftElement(
                name="major_duties",
                display_name="Major Duties",
                content="Duties content",
                status="approved",
            ).model_dump(),
            DraftElement(
                name="factor_1_knowledge",
                display_name="Factor 1: Knowledge",
                content="Knowledge content",
                status="approved",
            ).model_dump(),
        ]

        from langchain_core.messages import HumanMessage

        state = {
            "draft_elements": elements,
            "messages": [HumanMessage(content="Make some changes")],
        }

        result = await handle_element_revision_request(state)

        # Should ask for clarification when request is vague with multiple options
        # Either asks which section OR has low confidence and asks
        msg_lower = result["messages"][0].content.lower()
        assert ("which" in msg_lower and "section" in msg_lower) or \
               "certain" in msg_lower or "clarify" in msg_lower or \
               result.get("current_element_name") is None, \
               f"Expected clarification request, got: {result['messages'][0].content}"

    @skip_without_llm
    async def test_marks_element_for_revision(self):
        """Should mark the identified element for revision."""
        elements = [
            DraftElement(
                name="major_duties",
                display_name="Major Duties",
                content="Duties content",
                status="approved",
            ).model_dump()
        ]

        from langchain_core.messages import HumanMessage

        state = {
            "draft_elements": elements,
            "messages": [HumanMessage(content="Add more detail to major duties")],
        }

        result = await handle_element_revision_request(state)

        # Check that element was marked for revision
        updated_elements = result["draft_elements"]
        element = DraftElement.model_validate(updated_elements[0])
        assert element.status == "needs_revision"
        assert "more detail" in element.feedback.lower()


class TestCheckAllElementsComplete:
    """Tests for check_all_elements_complete function."""

    def test_returns_false_for_empty_list(self):
        """Should return False for empty element list."""
        assert check_all_elements_complete([]) is False

    def test_returns_true_when_all_approved(self):
        """Should return True when all elements are approved."""
        elements = [
            DraftElement(name="intro", display_name="Intro", status="approved").model_dump(),
            DraftElement(name="duties", display_name="Duties", status="approved").model_dump(),
        ]

        assert check_all_elements_complete(elements) is True

    def test_returns_true_when_all_qa_passed(self):
        """Should return True when all elements passed QA."""
        elements = [
            DraftElement(name="intro", display_name="Intro", status="qa_passed").model_dump(),
            DraftElement(name="duties", display_name="Duties", status="qa_passed").model_dump(),
        ]

        assert check_all_elements_complete(elements) is True

    def test_returns_true_for_mixed_complete_statuses(self):
        """Should return True for mix of approved and qa_passed."""
        elements = [
            DraftElement(name="intro", display_name="Intro", status="approved").model_dump(),
            DraftElement(name="duties", display_name="Duties", status="qa_passed").model_dump(),
        ]

        assert check_all_elements_complete(elements) is True

    def test_returns_false_when_any_incomplete(self):
        """Should return False when any element is incomplete."""
        elements = [
            DraftElement(name="intro", display_name="Intro", status="approved").model_dump(),
            DraftElement(name="duties", display_name="Duties", status="pending").model_dump(),
        ]

        assert check_all_elements_complete(elements) is False

    def test_returns_false_for_needs_revision(self):
        """Should return False when element needs revision."""
        elements = [
            DraftElement(name="intro", display_name="Intro", status="needs_revision").model_dump(),
        ]

        assert check_all_elements_complete(elements) is False


class TestGetIncompleteElements:
    """Tests for get_incomplete_elements function."""

    def test_returns_empty_for_all_complete(self):
        """Should return empty list when all complete."""
        elements = [
            DraftElement(name="intro", display_name="Intro", status="approved").model_dump(),
            DraftElement(name="duties", display_name="Duties", status="qa_passed").model_dump(),
        ]

        result = get_incomplete_elements(elements)

        assert result == []

    def test_returns_incomplete_display_names(self):
        """Should return display names of incomplete elements."""
        elements = [
            DraftElement(name="intro", display_name="Introduction", status="approved").model_dump(),
            DraftElement(name="duties", display_name="Major Duties", status="pending").model_dump(),
            DraftElement(name="factor_1", display_name="Factor 1", status="needs_revision").model_dump(),
        ]

        result = get_incomplete_elements(elements)

        assert "Major Duties" in result
        assert "Factor 1" in result
        assert "Introduction" not in result

    def test_handles_empty_list(self):
        """Should handle empty element list."""
        result = get_incomplete_elements([])
        assert result == []
