"""Intent classification models for user input analysis."""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# Intent type for reuse
IntentType = Literal[
    "provide_information",
    "ask_question",
    "confirm",
    "reject",
    "modify_answer",
    "request_restart",
    "request_export",
    "quit",
    "unrecognized",
]

# Export format type
ExportFormat = Literal["markdown", "word", "none"]


class FieldMapping(BaseModel):
    """
    Maps user input to a specific interview field.

    Used by intent classification to extract structured data
    from natural language user responses.
    """

    field_name: str = Field(..., description="Name of the interview field this maps to")
    extracted_value: str = Field(
        ..., description="Raw extracted text from user input"
    )
    parsed_value: Any = Field(
        ..., description="Structured/parsed value (e.g., list for organization)"
    )
    raw_input: str = Field(
        ..., description="The exact text this was extracted from"
    )
    needs_confirmation: bool = Field(
        default=False,
        description="Flag if extraction is uncertain and needs user confirmation",
    )


class Question(BaseModel):
    """A question extracted from user input."""

    text: str = Field(..., description="The question being asked")
    is_hr_specific: bool = Field(
        default=False, description="Whether the question is HR/policy specific"
    )
    is_process_question: bool = Field(
        default=False, description="Whether the question is about the PD process"
    )


class FieldModification(BaseModel):
    """A request to modify a previously provided field value."""

    field_name: str = Field(..., description="Which field the user wants to change")
    new_value: str = Field(..., description="The new value for the field")
    reason: Optional[str] = Field(
        default=None, description="Why the user wants to change it, if stated"
    )


class ElementModification(BaseModel):
    """A request to modify a draft element during review phase."""

    element_name: str = Field(
        ...,
        description="Name of the draft element to modify (e.g., 'introduction', 'major_duties', 'factor_1')"
    )
    feedback: str = Field(
        ...,
        description="User's feedback or requested changes for the element"
    )
    is_full_rewrite: bool = Field(
        default=False,
        description="Whether user wants complete rewrite vs specific changes"
    )


class ExportRequest(BaseModel):
    """A request to export the position description document."""

    format: ExportFormat = Field(
        default="none",
        description="Requested export format: 'markdown', 'word', or 'none'"
    )


class IntentClassification(BaseModel):
    """
    LLM output for intent classification.

    Structured output model for analyzing user messages and
    determining their intent during the conversation. Supports
    multiple intents in a single message (e.g., "Yes, and the grade is GS-13"
    contains both confirm and provide_information).
    """

    primary_intent: IntentType = Field(
        ...,
        description="The primary/dominant intent for routing purposes",
    )

    secondary_intents: list[IntentType] = Field(
        default_factory=list,
        description="Additional intents present in the message",
    )

    confidence: float = Field(
        ge=0, le=1, description="Confidence score for the classification"
    )

    # Extracted information (can contain multiple items)
    field_mappings: list[FieldMapping] = Field(
        default_factory=list,
        description="All field values extracted from the message",
    )

    # Questions (can contain multiple)
    questions: list[Question] = Field(
        default_factory=list,
        description="All questions asked in the message",
    )

    # Modifications (can contain multiple)
    modifications: list[FieldModification] = Field(
        default_factory=list,
        description="All field modification requests in the message",
    )

    # Element modifications (review phase)
    element_modifications: list[ElementModification] = Field(
        default_factory=list,
        description="Draft element modification requests during review phase",
    )

    # Export request (complete phase)
    export_request: Optional[ExportRequest] = Field(
        default=None,
        description="Export request extracted from message during complete phase",
    )

    @property
    def all_intents(self) -> list[IntentType]:
        """Get all intents (primary + secondary) in order."""
        return [self.primary_intent] + self.secondary_intents

    @property
    def has_multiple_intents(self) -> bool:
        """Check if message contains multiple intents."""
        return len(self.secondary_intents) > 0

    @property
    def has_information(self) -> bool:
        """Check if any field information was extracted."""
        return len(self.field_mappings) > 0

    @property
    def has_questions(self) -> bool:
        """Check if any questions were asked."""
        return len(self.questions) > 0

    @property
    def has_modifications(self) -> bool:
        """Check if any modification requests were made."""
        return len(self.modifications) > 0

    @property
    def has_element_modifications(self) -> bool:
        """Check if any element modification requests were made."""
        return len(self.element_modifications) > 0

    @property
    def element_to_modify(self) -> Optional[str]:
        """Get first element name to modify (convenience property)."""
        return self.element_modifications[0].element_name if self.element_modifications else None

    @property
    def element_feedback(self) -> Optional[str]:
        """Get first element feedback (convenience property)."""
        return self.element_modifications[0].feedback if self.element_modifications else None

    @property
    def is_confirmation(self) -> bool:
        """Check if this contains a confirmation intent."""
        return "confirm" in self.all_intents

    @property
    def is_rejection(self) -> bool:
        """Check if this contains a rejection intent."""
        return "reject" in self.all_intents

    @property
    def is_exit_intent(self) -> bool:
        """Check if user wants to exit the conversation."""
        return self.primary_intent in ("quit", "request_restart")

    @property
    def is_export_request(self) -> bool:
        """Check if this is an export request."""
        return self.primary_intent == "request_export"

    @property
    def export_format(self) -> Optional[ExportFormat]:
        """Get the requested export format if this is an export request."""
        if self.export_request:
            return self.export_request.format
        return None

    # Backwards compatibility properties
    @property
    def question(self) -> Optional[str]:
        """Get first question text (backwards compatibility)."""
        return self.questions[0].text if self.questions else None

    @property
    def is_hr_specific(self) -> Optional[bool]:
        """Get first question's HR flag (backwards compatibility)."""
        return self.questions[0].is_hr_specific if self.questions else None

    @property
    def is_process_question(self) -> Optional[bool]:
        """Get first question's process flag (backwards compatibility)."""
        return self.questions[0].is_process_question if self.questions else None

    @property
    def field_to_modify(self) -> Optional[str]:
        """Get first modification field (backwards compatibility)."""
        return self.modifications[0].field_name if self.modifications else None

    @property
    def new_value(self) -> Optional[str]:
        """Get first modification value (backwards compatibility)."""
        return self.modifications[0].new_value if self.modifications else None
