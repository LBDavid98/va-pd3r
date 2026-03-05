"""Interview tools for LLM-driven field collection.

These tools enable the LLM to decide what action to take during the interview phase
using the ReAct pattern, rather than heuristic routing logic.

The LLM sees state-aware prompts that tell it:
- What phase we're in
- What field we're currently collecting
- What fields have been collected/confirmed

Based on this context, the LLM chooses which tool to call.
"""

import logging
from typing import Annotated, Any, Optional

from langchain_core.tools import InjectedToolArg, tool
from pydantic import BaseModel, Field

from src.config.intake_fields import INTAKE_FIELDS, BASE_INTAKE_SEQUENCE
from src.models.interview import InterviewData, InterviewElement

logger = logging.getLogger(__name__)


class FieldAnswer(BaseModel):
    """Structured response for saving a field answer."""

    field_name: str = Field(
        ...,
        description="The name of the interview field being answered (e.g., 'position_title', 'grade', 'series')",
    )
    value: Any = Field(
        ...,
        description="The extracted value from the user's response. Type depends on field_type.",
    )
    raw_input: str = Field(
        ...,
        description="The original user text this value was extracted from.",
    )
    needs_confirmation: bool = Field(
        default=False,
        description="Set to True if the extraction is uncertain and needs user confirmation.",
    )


class FieldConfirmation(BaseModel):
    """Structured response for confirming a field value."""

    field_name: str = Field(
        ...,
        description="The name of the field being confirmed.",
    )


class QuestionAnswer(BaseModel):
    """Structured response for answering a user question."""

    question: str = Field(
        ...,
        description="The user's question.",
    )
    is_hr_specific: bool = Field(
        default=False,
        description="True if this is an HR/federal classification question requiring RAG lookup.",
    )


@tool
def save_field_answer(
    field_name: str,
    value: Any,
    raw_input: str,
    needs_confirmation: bool = False,
) -> str:
    """Save the user's answer to an interview field.

    Use this tool when the user provides information about their position
    that maps to one of the interview fields. The system prompt tells you
    which field we're currently collecting.

    Args:
        field_name: The interview field name (e.g., 'position_title', 'grade', 'series')
        value: The extracted/parsed value from the user's response
        raw_input: The original text the user provided
        needs_confirmation: Set True if extraction is uncertain

    Returns:
        Confirmation message about what was saved
    """
    # Validate field_name exists
    if field_name not in INTAKE_FIELDS:
        valid_fields = list(INTAKE_FIELDS.keys())
        return f"Error: Unknown field '{field_name}'. Valid fields are: {valid_fields}"

    field_def = INTAKE_FIELDS[field_name]

    # Basic type coercion based on field_type
    if field_def.field_type == "boolean" and isinstance(value, str):
        value = value.lower() in ("yes", "true", "1", "y")
    elif field_def.field_type == "integer" and isinstance(value, str):
        try:
            value = int(value)
        except ValueError:
            return f"Error: Could not convert '{value}' to integer for field '{field_name}'"
    elif field_def.field_type == "list" and isinstance(value, str):
        # Split on common delimiters
        value = [v.strip() for v in value.replace(";", ",").split(",") if v.strip()]

    status = "needs confirmation" if needs_confirmation else "confirmed"
    logger.info(f"Tool save_field_answer: {field_name}={value} ({status})")

    return f"Saved {field_name}: {value} (status: {status})"


@tool
def confirm_field_value(field_name: str) -> str:
    """Confirm a previously saved field value that needed confirmation.

    Use this tool when the user explicitly confirms a value that was
    marked as needing confirmation (uncertain extraction).

    Args:
        field_name: The name of the field to confirm

    Returns:
        Confirmation message
    """
    if field_name not in INTAKE_FIELDS:
        return f"Error: Unknown field '{field_name}'"

    logger.info(f"Tool confirm_field_value: {field_name}")
    return f"Confirmed value for {field_name}"


@tool
def answer_user_question(question: str, is_hr_specific: bool = False) -> str:
    """Answer a question from the user about the PD process or HR topics.

    Use this tool when the user asks a question rather than providing
    information. The is_hr_specific flag determines whether to use
    RAG lookup for federal HR knowledge.

    Examples of HR-specific questions (set is_hr_specific=True):
    - "What is FES?"
    - "How are grades determined?"
    - "What are the factor levels for a GS-13?"
    
    Examples of process questions (is_hr_specific=False):
    - "What information do you need from me?"
    - "How long will this take?"
    - "Can I go back and change an answer?"

    Args:
        question: The user's question
        is_hr_specific: True for HR/classification questions that need RAG

    Returns:
        Answer to the user's question, with citations if HR-specific
    """
    if is_hr_specific:
        # Use RAG to answer HR-specific questions
        logger.info(f"Tool answer_user_question (HR/RAG): {question[:50]}...")
        
        from src.tools.rag_tools import format_rag_context, get_source_citations, rag_lookup
        
        results = rag_lookup(question, k=4)
        
        if not results:
            return (
                "I don't have specific documentation on that topic in my knowledge base. "
                "For detailed HR policy questions, I'd recommend consulting your HR office "
                "or reviewing OPM.gov directly. However, I can try to answer based on "
                "general federal classification knowledge."
            )
        
        context = format_rag_context(results)
        citations = get_source_citations(results)
        
        # Format response with context and citations
        response = f"Based on the OPM guidance:\n\n{context}"
        if citations:
            response += f"\n\n📚 Sources: {', '.join(citations)}"
        
        return response
    else:
        # Process questions - provide helpful guidance about the PD writing process
        logger.info(f"Tool answer_user_question (process): {question[:50]}...")
        
        # Common process questions with helpful responses
        question_lower = question.lower()
        
        if any(word in question_lower for word in ["need", "collect", "information", "ask"]):
            return (
                "I'll be collecting information about: your position title, GS series and grade, "
                "organization, supervisory status, major duties, and other position details. "
                "Feel free to provide information in any order - I'll track what we've covered."
            )
        
        if any(word in question_lower for word in ["long", "time", "take"]):
            return (
                "The interview typically takes 10-20 minutes depending on position complexity. "
                "We'll go through each required field, and you can ask questions at any time."
            )
        
        if any(word in question_lower for word in ["change", "back", "modify", "correct"]):
            return (
                "Yes! You can change any previous answer at any time. Just tell me what you'd "
                "like to update, for example: 'Actually, change the grade to GS-14'."
            )
        
        if any(word in question_lower for word in ["skip", "later", "don't know"]):
            return (
                "For required fields, I do need the information to create a complete PD. "
                "However, you can say 'I'll need to check on that' and we can come back to it. "
                "For optional fields, you can skip them."
            )
        
        # Generic process response
        return (
            "I'm here to help create your position description. Feel free to ask about "
            "the process, what information I need, or any HR/classification questions. "
            "For specific federal policy questions, I can search the OPM knowledge base."
        )


@tool
def check_interview_complete(
    required_fields: Annotated[list[str], InjectedToolArg] = None,
) -> str:
    """Check if all required interview fields have been collected.

    Use this tool when you think all required fields have been provided
    and want to verify before transitioning to requirements confirmation.

    The tool will check against the required fields list and return
    which fields are still missing or need confirmation.

    Returns:
        Status message indicating completion or listing missing fields
    """
    # In actual implementation, this would check against state
    # For now, return a placeholder that the agent node will handle
    logger.info("Tool check_interview_complete called")
    return "[Check interview completion - will be handled by agent node]"


@tool
def request_field_clarification(field_name: str, clarification_request: str) -> str:
    """Request clarification from the user about a specific field.

    Use this tool when the user's response is ambiguous or incomplete
    for a particular field, and you need more information.

    Args:
        field_name: The field needing clarification
        clarification_request: What specific clarification is needed

    Returns:
        Message to present to user
    """
    if field_name not in INTAKE_FIELDS:
        return f"Error: Unknown field '{field_name}'"

    field_def = INTAKE_FIELDS[field_name]
    logger.info(f"Tool request_field_clarification: {field_name} - {clarification_request}")

    return f"[Clarification needed for {field_name}]: {clarification_request}"


@tool
def modify_field_value(
    field_name: str,
    new_value: Any,
    raw_input: str,
    reason: str = "",
) -> str:
    """Modify a previously saved field value.

    Use this tool when the user wants to change or correct a value
    they previously provided.

    Args:
        field_name: The field to modify
        new_value: The new value to set
        raw_input: The original user text for this modification
        reason: Optional reason for the modification

    Returns:
        Confirmation of modification
    """
    if field_name not in INTAKE_FIELDS:
        return f"Error: Unknown field '{field_name}'"

    logger.info(f"Tool modify_field_value: {field_name}={new_value} (reason: {reason})")
    return f"Modified {field_name} to: {new_value}"


# Export all interview tools for use in agent creation
INTERVIEW_TOOLS = [
    save_field_answer,
    confirm_field_value,
    answer_user_question,
    check_interview_complete,
    request_field_clarification,
    modify_field_value,
]


def get_next_required_field(
    interview_data: InterviewData,
    required_fields: list[str] = None,
) -> Optional[str]:
    """Get the next required field that hasn't been collected.

    Args:
        interview_data: Current interview data with collected values
        required_fields: List of required field names (defaults to BASE_INTAKE_SEQUENCE)

    Returns:
        Name of next field to collect, or None if all complete
    """
    if required_fields is None:
        required_fields = BASE_INTAKE_SEQUENCE

    # Get fields that need values or confirmation
    unset = interview_data.get_unset_required_fields(required_fields)
    if unset:
        return unset[0]

    needs_confirm = interview_data.get_fields_needing_confirmation()
    if needs_confirm:
        return needs_confirm[0]

    return None


def get_field_context(field_name: str) -> dict:
    """Get context information for a specific field.

    Returns field definition data useful for prompts.

    Args:
        field_name: The field to get context for

    Returns:
        Dict with prompt, user_guidance, examples, validation, etc.
    """
    if field_name not in INTAKE_FIELDS:
        return {}

    field = INTAKE_FIELDS[field_name]
    return {
        "field_name": field_name,
        "prompt": field.prompt,
        "user_guidance": field.user_guidance,
        "field_type": field.field_type,
        "required": field.required,
        "examples": field.examples,
        "validation": field.validation,
        "llm_guidance": field.llm_guidance,
    }


def get_interview_progress(
    interview_data: InterviewData,
    required_fields: list[str] = None,
) -> dict:
    """Get interview progress summary for prompts.

    Args:
        interview_data: Current interview data
        required_fields: List of required field names

    Returns:
        Dict with collected_fields, remaining_fields, fields_needing_confirmation
    """
    if required_fields is None:
        required_fields = BASE_INTAKE_SEQUENCE

    collected = interview_data.get_set_fields()
    remaining = interview_data.get_unset_required_fields(required_fields)
    needs_confirm = interview_data.get_fields_needing_confirmation()

    return {
        "collected_fields": collected,
        "remaining_fields": remaining,
        "fields_needing_confirmation": needs_confirm,
        "is_complete": len(remaining) == 0 and len(needs_confirm) == 0,
    }
