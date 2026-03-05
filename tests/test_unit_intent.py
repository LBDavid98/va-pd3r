"""Unit tests for intent classification models.

NOTE: Per ADR-005, this project does not use mock LLM implementations.
The classify_intent_basic function was removed - intent classification
must use the real LLM. Tests for the actual classify_intent function
should be integration tests that call the real LLM.
"""

import pytest

from src.models.intent import (
    ElementModification,
    FieldMapping,
    FieldModification,
    IntentClassification,
    Question,
)


class TestFieldMapping:
    """Tests for FieldMapping model."""

    def test_basic_field_mapping(self):
        """FieldMapping stores all required fields."""
        mapping = FieldMapping(
            field_name="grade",
            extracted_value="GS-12",
            parsed_value="GS-12",
            raw_input="It's a GS-12 position",
        )

        assert mapping.field_name == "grade"
        assert mapping.extracted_value == "GS-12"
        assert mapping.parsed_value == "GS-12"
        assert mapping.raw_input == "It's a GS-12 position"
        assert mapping.needs_confirmation is False

    def test_field_mapping_with_confirmation(self):
        """FieldMapping can flag uncertain extractions."""
        mapping = FieldMapping(
            field_name="series",
            extracted_value="2210",
            parsed_value="2210",
            raw_input="I think it's IT related",
            needs_confirmation=True,
        )

        assert mapping.needs_confirmation is True


class TestIntentClassification:
    """Tests for IntentClassification model."""

    def test_confirm_intent(self):
        """IntentClassification with confirm intent."""
        intent = IntentClassification(
            primary_intent="confirm",
            confidence=0.9,
        )

        assert intent.primary_intent == "confirm"
        assert intent.confidence == 0.9
        assert intent.is_confirmation is True
        assert intent.is_rejection is False
        assert intent.is_exit_intent is False

    def test_reject_intent(self):
        """IntentClassification with reject intent."""
        intent = IntentClassification(
            primary_intent="reject",
            confidence=0.85,
        )

        assert intent.is_rejection is True
        assert intent.is_confirmation is False

    def test_quit_intent(self):
        """IntentClassification with quit intent is exit."""
        intent = IntentClassification(
            primary_intent="quit",
            confidence=0.95,
        )

        assert intent.is_exit_intent is True

    def test_restart_intent(self):
        """IntentClassification with restart intent is exit."""
        intent = IntentClassification(
            primary_intent="request_restart",
            confidence=0.9,
        )

        assert intent.is_exit_intent is True

    def test_provide_info_with_mappings(self):
        """IntentClassification can include field mappings."""
        mappings = [
            FieldMapping(
                field_name="position_title",
                extracted_value="IT Specialist",
                parsed_value="IT Specialist",
                raw_input="I need an IT Specialist",
            ),
            FieldMapping(
                field_name="grade",
                extracted_value="GS-13",
                parsed_value="GS-13",
                raw_input="at the GS-13 level",
            ),
        ]

        intent = IntentClassification(
            primary_intent="provide_information",
            confidence=0.8,
            field_mappings=mappings,
        )

        assert intent.primary_intent == "provide_information"
        assert len(intent.field_mappings) == 2
        assert intent.field_mappings[0].field_name == "position_title"
        assert intent.has_information is True

    def test_ask_question_with_details(self):
        """IntentClassification captures question details."""
        intent = IntentClassification(
            primary_intent="ask_question",
            confidence=0.85,
            questions=[
                Question(
                    text="What is an occupational series?",
                    is_hr_specific=True,
                    is_process_question=False,
                )
            ],
        )

        assert intent.primary_intent == "ask_question"
        assert intent.has_questions is True
        # Backwards compatibility
        assert intent.question == "What is an occupational series?"
        assert intent.is_hr_specific is True

    def test_modify_answer_details(self):
        """IntentClassification captures modification details."""
        intent = IntentClassification(
            primary_intent="modify_answer",
            confidence=0.75,
            modifications=[
                FieldModification(
                    field_name="grade",
                    new_value="GS-14",
                )
            ],
        )

        assert intent.primary_intent == "modify_answer"
        assert intent.has_modifications is True
        # Backwards compatibility
        assert intent.field_to_modify == "grade"
        assert intent.new_value == "GS-14"

    def test_multiple_intents(self):
        """IntentClassification supports multiple intents."""
        intent = IntentClassification(
            primary_intent="confirm",
            secondary_intents=["provide_information"],
            confidence=0.9,
            field_mappings=[
                FieldMapping(
                    field_name="grade",
                    extracted_value="GS-13",
                    parsed_value="GS-13",
                    raw_input="Yes, and the grade is GS-13",
                )
            ],
        )

        assert intent.primary_intent == "confirm"
        assert intent.has_multiple_intents is True
        assert intent.all_intents == ["confirm", "provide_information"]
        assert intent.is_confirmation is True
        assert intent.has_information is True

    def test_question_with_info(self):
        """User asks question while providing information."""
        intent = IntentClassification(
            primary_intent="ask_question",
            secondary_intents=["provide_information"],
            confidence=0.85,
            questions=[
                Question(text="What's a series code?", is_hr_specific=True)
            ],
            field_mappings=[
                FieldMapping(
                    field_name="series",
                    extracted_value="2210",
                    parsed_value="2210",
                    raw_input="Mine is 2210",
                )
            ],
        )

        assert intent.has_questions is True
        assert intent.has_information is True
        assert len(intent.all_intents) == 2

    def test_multiple_modifications(self):
        """User requests multiple field changes at once."""
        intent = IntentClassification(
            primary_intent="modify_answer",
            confidence=0.8,
            modifications=[
                FieldModification(field_name="grade", new_value="GS-14"),
                FieldModification(field_name="series", new_value="2210"),
            ],
        )

        assert len(intent.modifications) == 2
        assert intent.modifications[0].field_name == "grade"
        assert intent.modifications[1].field_name == "series"


class TestElementModification:
    """Tests for ElementModification model and related properties."""

    def test_element_modification_creation(self):
        """ElementModification stores all fields correctly."""
        mod = ElementModification(
            element_name="introduction",
            feedback="Make it more formal",
            is_full_rewrite=False,
        )

        assert mod.element_name == "introduction"
        assert mod.feedback == "Make it more formal"
        assert mod.is_full_rewrite is False

    def test_element_modification_full_rewrite(self):
        """ElementModification can flag for full rewrite."""
        mod = ElementModification(
            element_name="major_duties",
            feedback="Completely redo this section",
            is_full_rewrite=True,
        )

        assert mod.is_full_rewrite is True

    def test_intent_with_element_modifications(self):
        """IntentClassification can include element modifications."""
        intent = IntentClassification(
            primary_intent="modify_answer",
            confidence=0.85,
            element_modifications=[
                ElementModification(
                    element_name="introduction",
                    feedback="Change the introduction to be more concise",
                    is_full_rewrite=True,
                )
            ],
        )

        assert intent.has_element_modifications is True
        assert intent.element_to_modify == "introduction"
        assert intent.element_feedback == "Change the introduction to be more concise"

    def test_intent_without_element_modifications(self):
        """IntentClassification handles missing element modifications."""
        intent = IntentClassification(
            primary_intent="confirm",
            confidence=0.9,
        )

        assert intent.has_element_modifications is False
        assert intent.element_to_modify is None
        assert intent.element_feedback is None

    def test_multiple_element_modifications(self):
        """IntentClassification can have multiple element modifications."""
        intent = IntentClassification(
            primary_intent="modify_answer",
            confidence=0.8,
            element_modifications=[
                ElementModification(
                    element_name="introduction",
                    feedback="More formal",
                ),
                ElementModification(
                    element_name="factor_1_knowledge",
                    feedback="Add more detail",
                ),
            ],
        )

        assert len(intent.element_modifications) == 2
        # Convenience properties return first
        assert intent.element_to_modify == "introduction"
