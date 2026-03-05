"""Prepare next node - generates the prompt for the next interview field or confirmation."""

from langchain_core.messages import AIMessage

from src.config.intake_fields import (
    BASE_INTAKE_SEQUENCE,
    INTAKE_FIELDS,
    SUPERVISORY_ADDITIONAL,
    get_intake_sequence,
)
from src.models.interview import InterviewData
from src.models.state import AgentState
from src.utils.llm import traced_node


def _get_field_prompt(field_name: str) -> str:
    """
    Get the user-friendly prompt for a field.

    Args:
        field_name: Name of the field

    Returns:
        User-facing prompt string
    """
    field_def = INTAKE_FIELDS.get(field_name)
    if field_def:
        # Prefer user_guidance over raw prompt for conversational flow
        return field_def.user_guidance or field_def.prompt
    return f"Please provide the {field_name.replace('_', ' ')}."


def _build_confirmation_prompt(
    field_name: str,
    value: any,
) -> str:
    """
    Build a confirmation prompt for an uncertain field value.

    Args:
        field_name: Name of the field to confirm
        value: The extracted value to confirm

    Returns:
        Confirmation prompt string
    """
    friendly_name = field_name.replace("_", " ")

    # Format value for display
    if isinstance(value, list):
        value_str = ", ".join(str(v) for v in value)
    elif isinstance(value, dict):
        value_str = "; ".join(f"{k}: {v}" for k, v in value.items())
    elif isinstance(value, bool):
        value_str = "Yes" if value else "No"
    else:
        value_str = str(value)

    return f"I captured **{friendly_name}** as: **{value_str}**. Is that correct?"


def _get_next_field_in_sequence(
    missing_fields: list[str],
    is_supervisor: bool | None,
) -> str | None:
    """
    Get the next field to ask based on sequence order.

    Args:
        missing_fields: List of fields still needed
        is_supervisor: Whether this is a supervisory position

    Returns:
        Next field name or None if complete
    """
    sequence = get_intake_sequence(is_supervisor)

    for field_name in sequence:
        if field_name in missing_fields:
            return field_name

    return None


def _format_interview_summary(interview: InterviewData) -> str:
    """
    Format a complete summary of collected interview data for user confirmation.

    Args:
        interview: The InterviewData instance

    Returns:
        Formatted summary string
    """
    summary_dict = interview.to_summary_dict()

    if not summary_dict:
        return "No information collected yet."

    lines = ["Here's what I have for your position description:", ""]

    # Group by category for cleaner display
    categories = {
        "Core Position Information": ["position_title", "series", "grade"],
        "Organization Context": ["organization", "organization_hierarchy", "reports_to"],
        "Position Duties": ["daily_activities", "major_duties"],
        "Supervisory Information": [
            "is_supervisor",
            "supervised_employees",
            "num_supervised",
            "percent_supervising",
        ],
        "Supervisory Factors": [
            "f1_program_scope",
            "f2_organizational_setting",
            "f3_supervisory_authorities",
            "f4_key_contacts",
            "f5_subordinate_details",
            "f6_special_conditions",
        ],
    }

    for category_name, field_names in categories.items():
        category_fields = [
            (name, summary_dict[name]) for name in field_names if name in summary_dict
        ]

        if category_fields:
            lines.append(f"**{category_name}**")
            for field_name, value in category_fields:
                friendly_name = field_name.replace("_", " ").title()

                # Format value
                if isinstance(value, list):
                    value_str = ", ".join(str(v) for v in value)
                elif isinstance(value, dict):
                    value_str = "; ".join(f"{k}: {v}" for k, v in value.items())
                elif isinstance(value, bool):
                    value_str = "Yes" if value else "No"
                else:
                    value_str = str(value)

                lines.append(f"  • {friendly_name}: {value_str}")
            lines.append("")

    return "\n".join(lines)


def _prepare_review_phase_prompt(state: AgentState) -> dict:
    """
    Prepare the prompt for the review phase.

    Shows the assembled document for final review and asks for
    user confirmation or revision requests.

    Args:
        state: Current agent state with draft_elements

    Returns:
        State update with review prompt
    """
    from src.models.draft import DraftElement
    from src.utils.document import assemble_final_document, create_review_summary

    draft_elements = state.get("draft_elements", [])
    interview_data = state.get("interview_data")

    if not draft_elements:
        return {
            "current_field": None,
            "next_prompt": "No draft elements available yet.",
            "messages": [AIMessage(content="No draft elements available yet.")],
        }

    # Generate the review summary
    review_summary = create_review_summary(draft_elements, interview_data)

    # Generate the assembled document
    assembled_doc = assemble_final_document(draft_elements, interview_data)

    # Build the review message
    review_message = (
        "🎉 **All sections have been drafted!**\n\n"
        "Here's your complete position description for final review:\n\n"
        "---\n\n"
        f"{assembled_doc}\n\n"
        "---\n\n"
        f"{review_summary}\n\n"
        "**What would you like to do?**\n"
        "- Say **'yes'** or **'approve'** to finalize the document\n"
        "- To revise a section, just tell me which one "
        "(e.g., 'change the introduction' or 'revise major duties')"
    )

    return {
        "current_field": None,
        "next_prompt": review_message,
        "messages": [AIMessage(content=review_message)],
    }


@traced_node
def prepare_next_node(state: AgentState) -> dict:
    """
    Prepare the next prompt for the user.

    This node determines what to ask next based on phase and state:

    **Interview phase:**
    1. If there's a validation error, re-prompt for the same field
    2. If fields need confirmation, ask for confirmation
    3. If fields are missing, ask for the next required field
    4. If all complete, signal completion check

    **Requirements phase (interview complete):**
    - Display the full interview summary
    - Ask "Does everything look ok?" for user confirmation
    - User must confirm before FES evaluation begins

    Args:
        state: Current agent state

    Returns:
        State update with next_prompt message and current_field
    """
    phase = state.get("phase", "init")
    
    # Transition from init to interview when first entering this node
    if phase == "init":
        phase = "interview"

    # Review phase: show assembled document for final review
    if phase == "review":
        return _prepare_review_phase_prompt(state)

    # Requirements phase: show summary and ask for confirmation
    if phase == "requirements":
        interview_dict = state.get("interview_data", {})
        if interview_dict:
            interview = InterviewData.model_validate(interview_dict)
            summary = _format_interview_summary(interview)

            confirmation_prompt = (
                f"{summary}\n\n"
                "Does this look correct? If everything's good, say **yes** and I'll start "
                "generating your position description. If you need to change anything, "
                "just let me know what to update."
            )

            return {
                "current_field": None,
                "validation_error": None,  # Clear validation errors
                "next_prompt": confirmation_prompt,
                "messages": [AIMessage(content=confirmation_prompt)],
            }

    # Check for validation errors first - re-prompt for the same field
    validation_error = state.get("validation_error")
    current_field = state.get("current_field")
    
    if validation_error and current_field:
        # Get the field prompt and append the error message
        field_prompt = _get_field_prompt(current_field)
        error_prompt = f"{field_prompt}\n\n(Previous entry was invalid: {validation_error})"
        
        return {
            "phase": phase,
            "current_field": current_field,
            "validation_error": None,  # Clear after displaying
            "next_prompt": error_prompt,
            "messages": [AIMessage(content=error_prompt)],
        }

    # Check for fields needing confirmation first
    fields_needing_confirmation = state.get("fields_needing_confirmation", [])

    if fields_needing_confirmation:
        # Get the first field needing confirmation
        field_name = fields_needing_confirmation[0]

        # Get the current value
        interview_dict = state.get("interview_data", {})
        if interview_dict:
            interview = InterviewData.model_validate(interview_dict)
            element = getattr(interview, field_name, None)
            if element and element.is_set:
                prompt = _build_confirmation_prompt(field_name, element.value)
                return {
                    "phase": phase,
                    "current_field": field_name,
                    "next_prompt": prompt,
                    "messages": [AIMessage(content=prompt)],
                }

    # Check for missing fields
    missing_fields = state.get("missing_fields", [])

    if missing_fields:
        # Determine is_supervisor status
        interview_dict = state.get("interview_data", {})
        is_supervisor = None
        if interview_dict:
            interview = InterviewData.model_validate(interview_dict)
            if interview.is_supervisor.is_set:
                is_supervisor = interview.is_supervisor.value

        # Get next field in sequence
        next_field = _get_next_field_in_sequence(missing_fields, is_supervisor)

        if next_field:
            prompt = _get_field_prompt(next_field)
            return {
                "phase": phase,
                "current_field": next_field,
                "next_prompt": prompt,
                "messages": [AIMessage(content=prompt)],
            }

    # All fields complete - transition directly to requirements phase
    # Instead of an intermediate "I think I have everything" message,
    # we go straight to showing the summary for confirmation
    interview_dict = state.get("interview_data", {})
    if interview_dict:
        interview = InterviewData.model_validate(interview_dict)
        summary = _format_interview_summary(interview)
        
        confirmation_prompt = (
            "🎉 **Interview Complete!**\n\n"
            f"{summary}\n\n"
            "Does this look correct? If everything's good, say **yes** and I'll start "
            "generating your position description. If you need to change anything, "
            "just let me know what to update."
        )
        
        return {
            "phase": "requirements",  # Transition to requirements phase
            "current_field": None,
            "validation_error": None,
            "next_prompt": confirmation_prompt,
            "messages": [AIMessage(content=confirmation_prompt)],
        }

    # Fallback if no interview data
    return {
        "phase": phase,
        "current_field": None,
        "next_prompt": "I think I have everything I need. Let me review what we've collected...",
        "messages": [AIMessage(content="I think I have everything I need. Let me review what we've collected...")],
    }
