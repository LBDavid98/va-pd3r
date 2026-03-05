"""Unit tests for export_node."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.nodes.export_node import (
    export_document_node,
    _extract_export_format,
)


# ============================================================================
# Test Data Fixtures
# ============================================================================


@pytest.fixture
def sample_interview_data():
    """Sample interview data for testing."""
    return {
        "position_title": {"value": "IT Specialist", "is_set": True},
        "series": {"value": "2210", "is_set": True},
        "grade": {"value": "13", "is_set": True},
        "organization": {
            "value": ["Department of Testing", "Office of Examples"],
            "is_set": True,
        },
        "reports_to": {"value": "Branch Chief", "is_set": True},
        "is_supervisor": {"value": False, "is_set": True},
        "major_duties": {"value": [], "is_set": False},
        "purpose": {"value": None, "is_set": False},
        "direct_reports": {"value": None, "is_set": False},
    }


@pytest.fixture
def sample_draft_elements():
    """Sample draft elements for testing."""
    return [
        {
            "name": "introduction",
            "display_name": "Introduction",
            "content": "This position serves as an IT Specialist.",
            "status": "approved",
            "revision_count": 0,
            "qa_passed": True,
        },
        {
            "name": "major_duties",
            "display_name": "Major Duties",
            "content": "- Administers IT systems\n- Provides support",
            "status": "approved",
            "revision_count": 0,
            "qa_passed": True,
        },
    ]


# ============================================================================
# _extract_export_format Tests
# ============================================================================


class TestExtractExportFormat:
    """Tests for _extract_export_format function."""

    def test_extracts_word_from_intent_classification(self):
        """Extract word format from structured intent."""
        state = {
            "intent_classification": {
                "export_request": {"format": "word"}
            }
        }

        result = _extract_export_format(state)

        assert result == "word"

    def test_extracts_markdown_from_intent_classification(self):
        """Extract markdown format from structured intent."""
        state = {
            "intent_classification": {
                "export_request": {"format": "markdown"}
            }
        }

        result = _extract_export_format(state)

        assert result == "markdown"

    def test_extracts_none_from_intent_classification(self):
        """Extract none format from structured intent."""
        state = {
            "intent_classification": {
                "export_request": {"format": "none"}
            }
        }

        result = _extract_export_format(state)

        assert result == "none"

    def test_falls_back_to_message_parsing_word(self):
        """Fall back to message parsing for word."""
        from langchain_core.messages import HumanMessage

        state = {
            "messages": [HumanMessage(content="word")]
        }

        result = _extract_export_format(state)

        assert result == "word"

    def test_falls_back_to_message_parsing_docx(self):
        """Fall back to message parsing for .docx."""
        from langchain_core.messages import HumanMessage

        state = {
            "messages": [HumanMessage(content="give me a .docx file")]
        }

        result = _extract_export_format(state)

        assert result == "word"

    def test_falls_back_to_message_parsing_markdown(self):
        """Fall back to message parsing for markdown."""
        from langchain_core.messages import HumanMessage

        state = {
            "messages": [HumanMessage(content="markdown please")]
        }

        result = _extract_export_format(state)

        assert result == "markdown"

    def test_falls_back_to_message_parsing_md(self):
        """Fall back to message parsing for .md."""
        from langchain_core.messages import HumanMessage

        state = {
            "messages": [HumanMessage(content="export as md")]
        }

        result = _extract_export_format(state)

        assert result == "markdown"

    def test_falls_back_to_message_parsing_done(self):
        """Fall back to message parsing for done."""
        from langchain_core.messages import HumanMessage

        state = {
            "messages": [HumanMessage(content="done")]
        }

        result = _extract_export_format(state)

        assert result == "none"

    def test_returns_unknown_for_unclear_message(self):
        """Return unknown for unclear messages."""
        from langchain_core.messages import HumanMessage

        state = {
            "messages": [HumanMessage(content="hello")]
        }

        result = _extract_export_format(state)

        assert result == "unknown"

    def test_returns_unknown_for_empty_state(self):
        """Return unknown for empty state."""
        state = {}

        result = _extract_export_format(state)

        assert result == "unknown"


# ============================================================================
# export_document_node Tests
# ============================================================================


class TestExportDocumentNode:
    """Tests for export_document_node function."""

    def test_none_format_skips_export(self, sample_draft_elements, sample_interview_data):
        """When format is none, skip export gracefully."""
        state = {
            "draft_elements": sample_draft_elements,
            "interview_data": sample_interview_data,
            "intent_classification": {
                "export_request": {"format": "none"}
            },
        }

        result = export_document_node(state)

        assert "No problem" in result["messages"][0].content
        # Note: "Would you like to write another" is now handled by end_conversation_node
        assert "saved and ready" in result["messages"][0].content

    def test_word_export_creates_file(self, sample_draft_elements, sample_interview_data):
        """Word export creates file and reports success."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.nodes.export_node.export_to_word") as mock_export:
                mock_export.return_value = Path(tmpdir) / "test.docx"

                state = {
                    "draft_elements": sample_draft_elements,
                    "interview_data": sample_interview_data,
                    "intent_classification": {
                        "export_request": {"format": "word"}
                    },
                }

                result = export_document_node(state)

                assert "Word format" in result["messages"][0].content
                # Note: "Would you like to write another" is now handled by end_conversation_node
                mock_export.assert_called_once()

    def test_markdown_export_creates_file(self, sample_draft_elements, sample_interview_data):
        """Markdown export creates file and reports success."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.nodes.export_node.export_to_markdown") as mock_export:
                mock_export.return_value = Path(tmpdir) / "test.md"

                state = {
                    "draft_elements": sample_draft_elements,
                    "interview_data": sample_interview_data,
                    "intent_classification": {
                        "export_request": {"format": "markdown"}
                    },
                }

                result = export_document_node(state)

                assert "Markdown format" in result["messages"][0].content
                # Note: "Would you like to write another" is now handled by end_conversation_node
                mock_export.assert_called_once()

    def test_word_export_handles_error(self, sample_draft_elements, sample_interview_data):
        """Word export handles errors gracefully."""
        with patch("src.nodes.export_node.export_to_word") as mock_export:
            mock_export.side_effect = Exception("Test error")

            state = {
                "draft_elements": sample_draft_elements,
                "interview_data": sample_interview_data,
                "intent_classification": {
                    "export_request": {"format": "word"}
                },
            }

            result = export_document_node(state)

            assert "error" in result["messages"][0].content.lower()
            assert "Test error" in result["messages"][0].content

    def test_unknown_format_asks_for_clarification(self, sample_draft_elements, sample_interview_data):
        """Unknown format asks for clarification."""
        from langchain_core.messages import HumanMessage

        state = {
            "draft_elements": sample_draft_elements,
            "interview_data": sample_interview_data,
            "messages": [HumanMessage(content="something unclear")],
        }

        result = export_document_node(state)

        assert "didn't understand" in result["messages"][0].content
        assert "word" in result["messages"][0].content.lower()
        assert "markdown" in result["messages"][0].content.lower()
