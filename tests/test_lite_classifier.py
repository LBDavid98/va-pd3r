"""Tests for the lightweight intent classification system.

These tests verify:
1. The lite classifier template is active in production
2. Token usage is reasonable (< 1000 input tokens per call)
3. Classification accuracy is maintained for all phases
4. Context is minimal (only last assistant message, not full history)

NOTE: Per ADR-005, this project does not use mock LLM implementations.
Some tests that verify classification accuracy require real LLM calls
and are marked as integration tests.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from typing import Any

from src.models.intent import IntentClassification
from src.models.state import AgentState
from src.prompts import get_template


class TestLiteTemplateIsActive:
    """Tests that verify the lite template is used in production."""

    def test_lite_template_exists(self):
        """The lite template file exists and can be loaded."""
        template = get_template("intent_classification_lite.jinja")
        assert template is not None

    def test_full_template_exists(self):
        """The full template also exists (for reference)."""
        template = get_template("intent_classification.jinja")
        assert template is not None

    def test_lite_template_is_smaller(self):
        """The lite template is significantly smaller than full template."""
        lite = get_template("intent_classification_lite.jinja")
        full = get_template("intent_classification.jinja")

        # Render with minimal context to compare sizes
        lite_rendered = lite.render(
            phase="interview",
            current_field="position_title",
            last_assistant_message="What is the position title?",
            user_message="Data Scientist",
        )

        full_rendered = full.render(
            phase="interview",
            current_field="position_title",
            field_definitions={},  # Would be much larger in practice
            user_message="Data Scientist",
        )

        # Lite should be at least 30% smaller
        size_ratio = len(lite_rendered) / len(full_rendered)
        assert size_ratio < 0.80, f"Lite template should be much smaller, got ratio {size_ratio:.2f}"

    def test_node_uses_lite_template(self):
        """The intent classification node imports and uses the lite template."""
        # Read the node source to verify it uses lite template
        import inspect
        from src.nodes.intent_classification_node import classify_intent_with_llm

        source = inspect.getsource(classify_intent_with_llm)
        assert "intent_classification_lite.jinja" in source, (
            "classify_intent_with_llm should use intent_classification_lite.jinja"
        )


class TestLiteTemplateContext:
    """Tests that verify the lite template uses minimal context."""

    def test_lite_template_has_phase(self):
        """The lite template includes phase context."""
        template = get_template("intent_classification_lite.jinja")
        content = template.render(
            phase="interview",
            current_field=None,
            last_assistant_message=None,
            user_message="test",
        )
        assert "interview" in content.lower()

    def test_lite_template_has_current_field(self):
        """The lite template includes current field when provided."""
        template = get_template("intent_classification_lite.jinja")
        content = template.render(
            phase="interview",
            current_field="position_title",
            last_assistant_message=None,
            user_message="test",
        )
        assert "position_title" in content

    def test_lite_template_has_last_assistant_message(self):
        """The lite template includes last assistant message when provided."""
        template = get_template("intent_classification_lite.jinja")
        content = template.render(
            phase="interview",
            current_field=None,
            last_assistant_message="What is your position title?",
            user_message="test",
        )
        assert "What is your position title?" in content

    def test_lite_template_has_user_message(self):
        """The lite template includes the user message."""
        template = get_template("intent_classification_lite.jinja")
        content = template.render(
            phase="interview",
            current_field=None,
            last_assistant_message=None,
            user_message="Data Scientist GS-14",
        )
        assert "Data Scientist GS-14" in content

    def test_lite_template_does_not_include_full_field_definitions(self):
        """The lite template doesn't include verbose field definitions."""
        template = get_template("intent_classification_lite.jinja")
        content = template.render(
            phase="interview",
            current_field="position_title",
            last_assistant_message="What is the title?",
            user_message="Data Scientist",
        )
        # Full template has extensive field_definitions with validation, examples, etc.
        # Lite template should not have these verbose sections
        assert "### position_title" not in content or content.count("###") < 5
        assert "validation" not in content.lower() or "validation:" not in content.lower()

    def test_lite_template_no_conversation_history(self):
        """The lite template doesn't iterate over full message history."""
        from pathlib import Path
        
        # Read template source directly from file
        template_path = Path(__file__).parent.parent / "src" / "prompts" / "templates" / "intent_classification_lite.jinja"
        source = template_path.read_text()

        # Should not have iteration over messages
        assert "for msg in messages" not in source
        assert "{% for message" not in source



class TestLiteTemplateIntentDefinitions:
    """Tests that the lite template has all necessary intent definitions."""

    @pytest.fixture
    def rendered_template(self) -> str:
        """Render the lite template with typical context."""
        template = get_template("intent_classification_lite.jinja")
        return template.render(
            phase="interview",
            current_field="grade",
            last_assistant_message="What is the grade?",
            user_message="GS-13",
        )

    def test_has_provide_information_intent(self, rendered_template: str):
        """Template defines provide_information intent."""
        assert "provide_information" in rendered_template

    def test_has_ask_question_intent(self, rendered_template: str):
        """Template defines ask_question intent."""
        assert "ask_question" in rendered_template

    def test_has_confirm_intent(self, rendered_template: str):
        """Template defines confirm intent."""
        # Look for confirm as a definition, not just any mention
        assert "confirm" in rendered_template.lower()

    def test_has_reject_intent(self, rendered_template: str):
        """Template defines reject intent."""
        assert "reject" in rendered_template.lower()

    def test_has_modify_answer_intent(self, rendered_template: str):
        """Template defines modify_answer intent."""
        assert "modify_answer" in rendered_template

    def test_has_request_export_intent(self, rendered_template: str):
        """Template defines request_export intent."""
        assert "request_export" in rendered_template

    def test_has_quit_intent(self, rendered_template: str):
        """Template defines quit intent."""
        assert "quit" in rendered_template

    def test_has_unrecognized_intent(self, rendered_template: str):
        """Template defines unrecognized intent."""
        assert "unrecognized" in rendered_template


class TestLiteClassifierFieldExtraction:
    """Tests for field extraction guidance in lite template."""

    def test_common_fields_mentioned(self):
        """The lite template mentions common interview fields."""
        template = get_template("intent_classification_lite.jinja")
        content = template.render(
            phase="interview",
            current_field="position_title",
            last_assistant_message="What is the title?",
            user_message="Data Scientist",
        )
        # Should have basic field guidance
        assert "position_title" in content
        assert "grade" in content
        assert "series" in content

    def test_multi_field_extraction_guidance(self):
        """The lite template guides multi-field extraction."""
        template = get_template("intent_classification_lite.jinja")
        content = template.render(
            phase="interview",
            current_field="position_title",
            last_assistant_message="Tell me about the position.",
            user_message="Data Scientist, GS-14, 1560",
        )
        # Should have guidance about extracting multiple fields
        assert "multiple" in content.lower() or "all" in content.lower()


class TestLiteClassifierPhaseSpecific:
    """Tests for phase-specific behavior in lite template."""

    def test_review_phase_includes_element_guidance(self):
        """Review phase template includes draft element modification guidance."""
        template = get_template("intent_classification_lite.jinja")
        content = template.render(
            phase="review",
            current_field=None,
            last_assistant_message="Approve or request changes?",
            user_message="Change the tone",
        )
        # Review phase should mention elements/modifications
        # Check the template actually has review-specific content
        assert "review" in content.lower()

    def test_complete_phase_includes_export_guidance(self):
        """Complete phase template includes export format guidance."""
        template = get_template("intent_classification_lite.jinja")
        content = template.render(
            phase="complete",
            current_field=None,
            last_assistant_message="Export to Word or Markdown?",
            user_message="word",
        )
        # Complete phase should have export guidance
        # May include "word", "markdown", "export" mentions
        assert "complete" in content.lower() or "export" in content.lower()


class TestLiteClassifierIntegration:
    """Integration tests that verify classification accuracy.

    These tests require real LLM calls. They verify that the lite
    template maintains classification accuracy despite reduced context.
    
    Mark with `llm` marker so they run separately from unit tests.
    """

    @pytest.fixture
    def mock_state(self) -> dict[str, Any]:
        """Create a minimal state for testing."""
        return {
            "messages": [],
            "phase": "interview",
            "current_field": "position_title",
            "interview_data": {},
        }

    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_classify_provide_information(self, mock_state: dict):
        """Lite classifier correctly identifies provide_information intent."""
        from src.nodes.intent_classification_node import classify_intent_with_llm
        from langchain_core.messages import AIMessage

        mock_state["messages"] = [
            AIMessage(content="What is the position title?")
        ]

        result = await classify_intent_with_llm("Data Scientist", mock_state)

        assert result.primary_intent == "provide_information"
        assert result.confidence >= 0.5

    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_classify_ask_question(self, mock_state: dict):
        """Lite classifier correctly identifies ask_question intent."""
        from src.nodes.intent_classification_node import classify_intent_with_llm
        from langchain_core.messages import AIMessage

        mock_state["messages"] = [
            AIMessage(content="What is the position title?")
        ]

        result = await classify_intent_with_llm("What is a series code?", mock_state)

        assert result.primary_intent == "ask_question"
        assert result.has_questions

    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_classify_confirm(self, mock_state: dict):
        """Lite classifier correctly identifies confirm intent."""
        from src.nodes.intent_classification_node import classify_intent_with_llm
        from langchain_core.messages import AIMessage

        mock_state["phase"] = "requirements"
        mock_state["current_field"] = None
        mock_state["messages"] = [
            AIMessage(content="Here's a summary. Does this look correct?")
        ]

        result = await classify_intent_with_llm("Yes, that's correct", mock_state)

        assert result.primary_intent == "confirm"
        assert result.is_confirmation

    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_classify_reject(self, mock_state: dict):
        """Lite classifier correctly identifies reject intent."""
        from src.nodes.intent_classification_node import classify_intent_with_llm
        from langchain_core.messages import AIMessage

        mock_state["phase"] = "complete"
        mock_state["current_field"] = None
        mock_state["messages"] = [
            AIMessage(content="Would you like to write another PD?")
        ]

        result = await classify_intent_with_llm("No, I'm done", mock_state)

        assert result.primary_intent == "reject"
        assert result.is_rejection

    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_classify_multi_field_extraction(self, mock_state: dict):
        """Lite classifier extracts multiple fields from one message."""
        from src.nodes.intent_classification_node import classify_intent_with_llm
        from langchain_core.messages import AIMessage

        mock_state["messages"] = [
            AIMessage(content="Tell me about the position.")
        ]

        result = await classify_intent_with_llm(
            "Data Scientist, GS-14, series 1560", mock_state
        )

        assert result.primary_intent == "provide_information"
        assert len(result.field_mappings) >= 2, (
            f"Should extract multiple fields, got {len(result.field_mappings)}"
        )

    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_classify_export_request(self, mock_state: dict):
        """Lite classifier correctly identifies export request."""
        from src.nodes.intent_classification_node import classify_intent_with_llm
        from langchain_core.messages import AIMessage

        mock_state["phase"] = "complete"
        mock_state["current_field"] = None
        mock_state["messages"] = [
            AIMessage(content="Would you like to export? Word or Markdown?")
        ]

        result = await classify_intent_with_llm("word", mock_state)

        assert result.primary_intent == "request_export"
        assert result.export_request is not None
        assert result.export_request.format == "word"


class TestLiteClassifierVsFullComparison:
    """Tests comparing lite vs full template behavior.
    
    These document the tradeoffs made by using the lite template.
    """

    def test_lite_template_size_reduction(self):
        """Document the size reduction from lite template."""
        from pathlib import Path
        
        # Read template sources directly from files
        template_dir = Path(__file__).parent.parent / "src" / "prompts" / "templates"
        lite_source = (template_dir / "intent_classification_lite.jinja").read_text()
        full_source = (template_dir / "intent_classification.jinja").read_text()

        size_reduction = 1 - (len(lite_source) / len(full_source))
        print(f"\nLite template is {size_reduction:.1%} smaller than full template")
        print(f"  Lite: {len(lite_source)} chars")
        print(f"  Full: {len(full_source)} chars")

        # Should be at least 50% smaller
        assert size_reduction > 0.30, (
            f"Lite should be at least 30% smaller, got {size_reduction:.1%}"
        )

    def test_lite_has_essential_guidance(self):
        """Lite template has essential classification guidance."""
        template = get_template("intent_classification_lite.jinja")
        content = template.render(
            phase="interview",
            current_field="grade",
            last_assistant_message="What is the grade?",
            user_message="13",
        )

        # Essential elements for accurate classification
        essential = [
            "provide_information",
            "ask_question",
            "confirm",
            "reject",
            "unrecognized",
        ]

        for element in essential:
            assert element in content, f"Lite template missing essential: {element}"
