"""Agent state definition."""

from typing import Annotated, Literal, Optional

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """
    PD3r agent state.

    Uses TypedDict for LangGraph reducer compatibility.
    Stores serialized Pydantic models as dicts for checkpointing.
    """

    # Message history (LangGraph managed)
    messages: Annotated[list, add_messages]

    # Conversation phase
    phase: Literal["init", "interview", "requirements", "drafting", "review", "complete"]

    # Interview tracking
    interview_data: Optional[dict]  # Serialized InterviewData
    current_field: Optional[str]  # Which field we're currently asking about
    missing_fields: list[str]  # Required fields not yet collected
    fields_needing_confirmation: list[str]  # Fields with uncertain extractions

    # Intent classification
    last_intent: Optional[str]  # Most recent classified intent
    intent_classification: Optional[object]  # Full IntentClassification for structured details
    pending_question: Optional[str]  # Question to answer before continuing
    
    # Field mappings extracted from intent classification (transient, cleared after mapping)
    _field_mappings: Optional[list[dict]]  # Extracted field values from user input

    # FES evaluation (Phase 3)
    fes_evaluation: Optional[dict]  # Serialized FESEvaluation

    # Requirements (gathered from interview data)
    draft_requirements: Optional[dict]  # Serialized DraftRequirements

    # Drafting
    draft_elements: list[dict]  # List of serialized DraftElement
    current_element_index: int  # Which element we're drafting
    current_element_name: Optional[str]  # Name of current element being drafted

    # Control flow
    should_end: bool  # Whether to end conversation
    next_prompt: str  # What agent should say next

    # Write another flow
    wants_another: Optional[bool]  # None = not asked, True/False after response
    is_restart: bool  # Signals init_node to reset interview data but keep session

    # Session resume flow
    is_resume: bool  # Signals init_node to show resume greeting (session restored from checkpoint)

    # Per-session word count overrides (set by frontend, used by generate_element_node)
    word_count_targets: Optional[dict]  # {section_name: int} overrides for TARGET_WORD_COUNTS

    # Error handling (4.5)
    validation_error: Optional[str]  # Field validation error message for user display
    last_error: Optional[str]  # Last error message (for recovery handling)
