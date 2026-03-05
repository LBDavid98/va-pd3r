"""Tests for document assembly utilities."""

import pytest

from src.models.draft import DraftElement, create_all_draft_elements
from src.models.interview import InterviewData
from src.utils.document import (
    assemble_final_document,
    create_review_summary,
    format_element_for_display,
    get_all_element_names,
    get_element_by_name,
    get_element_display_name,
    should_include_supervisory_elements,
)


class TestAssembleFinalDocument:
    """Tests for assemble_final_document function."""

    def test_empty_elements_returns_message(self):
        """Should return appropriate message for empty elements."""
        result = assemble_final_document([])
        assert "No draft elements" in result

    def test_assembles_elements_in_order(self):
        """Should assemble elements in the order provided."""
        elements = [
            DraftElement(
                name="introduction",
                display_name="Introduction",
                content="This is the intro.",
                status="approved",
            ).model_dump(),
            DraftElement(
                name="major_duties",
                display_name="Major Duties",
                content="These are the duties.",
                status="approved",
            ).model_dump(),
        ]

        result = assemble_final_document(elements)

        assert "## Introduction" in result
        assert "## Major Duties" in result
        assert "This is the intro." in result
        assert "These are the duties." in result
        # Check order
        assert result.index("Introduction") < result.index("Major Duties")

    def test_skips_empty_content_elements(self):
        """Should skip elements without content."""
        elements = [
            DraftElement(
                name="introduction",
                display_name="Introduction",
                content="Has content.",
                status="approved",
            ).model_dump(),
            DraftElement(
                name="major_duties",
                display_name="Major Duties",
                content="",  # Empty
                status="pending",
            ).model_dump(),
        ]

        result = assemble_final_document(elements)

        assert "Introduction" in result
        assert "Has content." in result
        assert "Major Duties" not in result

    def test_includes_header_from_interview_data(self):
        """Should include document header from interview data."""
        elements = [
            DraftElement(
                name="introduction",
                display_name="Introduction",
                content="Content here.",
                status="approved",
            ).model_dump()
        ]

        interview = InterviewData()
        interview.position_title.set_value("IT Specialist")
        interview.series.set_value("2210")
        interview.grade.set_value("13")
        interview.organization.set_value(["Agency", "Office", "Division"])

        result = assemble_final_document(elements, interview.model_dump())

        assert "Position Description" in result
        assert "IT Specialist" in result
        assert "2210" in result
        assert "Agency" in result


class TestCreateReviewSummary:
    """Tests for create_review_summary function."""

    def test_empty_elements_returns_message(self):
        """Should return message for empty elements."""
        result = create_review_summary([])
        assert "No draft elements" in result

    def test_shows_element_status_summary(self):
        """Should show status counts and per-element status."""
        elements = [
            DraftElement(
                name="introduction",
                display_name="Introduction",
                content="Intro content",
                status="approved",
            ).model_dump(),
            DraftElement(
                name="major_duties",
                display_name="Major Duties",
                content="Duties content",
                status="qa_passed",
            ).model_dump(),
            DraftElement(
                name="factor_1",
                display_name="Factor 1",
                content="Factor content",
                status="needs_revision",
            ).model_dump(),
        ]

        result = create_review_summary(elements)

        assert "Total Sections" in result
        assert "3" in result
        assert "Approved" in result
        assert "Introduction" in result
        assert "approved" in result

    def test_includes_status_icons(self):
        """Should include status icons for visual indication."""
        elements = [
            DraftElement(
                name="introduction",
                display_name="Introduction",
                content="Content",
                status="approved",
            ).model_dump()
        ]

        result = create_review_summary(elements)

        assert "✅" in result  # Approved icon


class TestGetElementByName:
    """Tests for get_element_by_name function."""

    def test_finds_element_by_exact_name(self):
        """Should find element by exact name match."""
        elements = [
            DraftElement(name="introduction", display_name="Introduction").model_dump(),
            DraftElement(name="major_duties", display_name="Major Duties").model_dump(),
        ]

        idx, element = get_element_by_name(elements, "major_duties")

        assert idx == 1
        assert element is not None
        assert element.name == "major_duties"

    def test_finds_element_by_display_name(self):
        """Should find element by display name."""
        elements = [
            DraftElement(name="introduction", display_name="Introduction").model_dump(),
            DraftElement(name="major_duties", display_name="Major Duties").model_dump(),
        ]

        idx, element = get_element_by_name(elements, "Major Duties")

        assert idx == 1
        assert element is not None
        assert element.name == "major_duties"

    def test_finds_element_by_partial_match(self):
        """Should find element by partial name match."""
        elements = [
            DraftElement(name="factor_1_knowledge", display_name="Factor 1: Knowledge").model_dump(),
        ]

        idx, element = get_element_by_name(elements, "factor_1")

        assert idx == 0
        assert element is not None

    def test_returns_negative_for_not_found(self):
        """Should return -1 and None when not found."""
        elements = [
            DraftElement(name="introduction", display_name="Introduction").model_dump(),
        ]

        idx, element = get_element_by_name(elements, "nonexistent")

        assert idx == -1
        assert element is None

    def test_handles_empty_list(self):
        """Should handle empty element list."""
        idx, element = get_element_by_name([], "anything")

        assert idx == -1
        assert element is None


class TestShouldIncludeSupervisoryElements:
    """Tests for should_include_supervisory_elements function."""

    def test_returns_false_for_none(self):
        """Should return False when interview_data is None."""
        assert should_include_supervisory_elements(None) is False

    def test_returns_false_for_non_supervisory(self):
        """Should return False for non-supervisory positions."""
        interview = InterviewData()
        interview.is_supervisor.set_value(False)

        assert should_include_supervisory_elements(interview.model_dump()) is False

    def test_returns_true_for_supervisory(self):
        """Should return True for supervisory positions."""
        interview = InterviewData()
        interview.is_supervisor.set_value(True)

        assert should_include_supervisory_elements(interview.model_dump()) is True

    def test_returns_false_when_not_set(self):
        """Should return False when is_supervisor not set."""
        interview = InterviewData()

        assert should_include_supervisory_elements(interview.model_dump()) is False


class TestFormatElementForDisplay:
    """Tests for format_element_for_display function."""

    def test_includes_display_name_as_header(self):
        """Should include display name as header."""
        element = DraftElement(
            name="introduction",
            display_name="Introduction",
            content="Test content here.",
            status="approved",
        )

        result = format_element_for_display(element)

        assert "### Introduction" in result
        assert "Test content here." in result

    def test_shows_status_for_non_approved(self):
        """Should show status for non-approved elements."""
        element = DraftElement(
            name="introduction",
            display_name="Introduction",
            content="Content",
            status="needs_revision",
        )

        result = format_element_for_display(element)

        assert "needs_revision" in result

    def test_includes_qa_notes(self):
        """Should include QA notes if present."""
        element = DraftElement(
            name="introduction",
            display_name="Introduction",
            content="Content",
            status="needs_revision",
            qa_notes=["Missing required statement", "Consider adding more detail"],
        )

        result = format_element_for_display(element)

        assert "QA Notes" in result
        assert "Missing required statement" in result


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_get_all_element_names(self):
        """Should return all element names in order."""
        names = get_all_element_names()

        assert "introduction" in names
        assert "major_duties" in names
        assert "factor_1_knowledge" in names
        assert "other_significant_factors" in names
        # Check order
        assert names.index("introduction") < names.index("major_duties")

    def test_get_element_display_name_known(self):
        """Should return correct display name for known elements."""
        assert get_element_display_name("introduction") == "Introduction"
        assert get_element_display_name("major_duties") == "Major Duties and Responsibilities"
        assert get_element_display_name("factor_1_knowledge") == "Factor 1: Knowledge Required"

    def test_get_element_display_name_unknown(self):
        """Should generate display name for unknown elements."""
        result = get_element_display_name("some_custom_element")
        assert result == "Some Custom Element"
