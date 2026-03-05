"""Answer mapping node - applies extracted field values to interview state.

Includes error handling that routes to error_handler on unexpected failures.
"""

import logging
from typing import Any

from langchain_core.messages import AIMessage

from src.config.intake_fields import (
    BASE_INTAKE_SEQUENCE,
    INTAKE_FIELDS,
    SUPERVISORY_ADDITIONAL,
    get_intake_sequence,
)
from src.models.interview import InterviewData, InterviewElement
from src.models.state import AgentState
from src.utils.llm import traced_node
from src.validation import validate_grade, validate_series

logger = logging.getLogger(__name__)


# Fields that require validation before accepting
VALIDATED_FIELDS = {
    "series": validate_series,
    "grade": validate_grade,
}


def _parse_field_value(field_name: str, raw_value: str) -> Any:
    """
    Parse a raw string value into the appropriate type for a field.
    
    This handles basic type conversion based on field metadata from INTAKE_FIELDS.
    For more sophisticated extraction, the LLM-based extractor should be used.
    
    Args:
        field_name: Name of the field
        raw_value: Raw string value from user
        
    Returns:
        Parsed value in appropriate type
    """
    field_def = INTAKE_FIELDS.get(field_name)
    if not field_def:
        return raw_value.strip()
    
    field_type = field_def.field_type
    value = raw_value.strip()
    
    if field_type == "boolean":
        # Convert yes/no style answers to boolean
        lower_val = value.lower()
        if lower_val in ("yes", "y", "true", "1"):
            return True
        elif lower_val in ("no", "n", "false", "0"):
            return False
        # Try to infer from content
        if any(word in lower_val for word in ["supervisor", "supervise", "manage"]):
            return True
        return False
    
    elif field_type == "integer":
        # Extract first number from value
        import re
        numbers = re.findall(r'\d+', value)
        if numbers:
            return int(numbers[0])
        return 0
    
    elif field_type == "list":
        # Split by common delimiters
        import re
        # Split on commas, semicolons, or "and"
        items = re.split(r'[,;]|\band\b', value)
        return [item.strip() for item in items if item.strip()]
    
    elif field_type == "dict":
        # Parse duty-percentage format: "Duty 40%; Another duty 30%"
        # But return as list for InterviewData compatibility
        import re
        result = []
        # Pattern matches: "description XX%" or "description: XX%"
        pattern = r'([^;,%]+?)\s*[:=]?\s*(\d+)\s*%?(?:[,;]|$)'
        matches = re.findall(pattern, value)
        for desc, pct in matches:
            desc = desc.strip()
            if desc:
                result.append(f"{desc} ({pct}%)")
        
        # If no pattern matches, split by semicolons/commas
        if not result:
            items = re.split(r'[;,]', value)
            result = [item.strip() for item in items if item.strip()]
        
        return result if result else [value]
    
    else:
        # String or text - return cleaned value
        return value


def _normalize_field_value(field_name: str, value: Any) -> Any:
    """
    Normalize a parsed value to match the expected type for a field.
    
    This handles cases where the LLM returns a different format than expected,
    e.g., dict instead of list for major_duties, or int instead of str for grade.
    
    Args:
        field_name: Name of the field
        value: Parsed value from LLM
        
    Returns:
        Normalized value in the correct format
    """
    # Grade field expects string but LLM often returns integer
    if field_name == "grade":
        if isinstance(value, int):
            return str(value)
        elif isinstance(value, str):
            return value
        return str(value) if value is not None else value
    
    # Series field should also be string
    if field_name == "series":
        if isinstance(value, int):
            return str(value)
        return str(value) if value is not None else value
    
    # Fields that expect list[str] but LLM might return dict or list of dicts
    list_fields = {"major_duties", "daily_activities", "organization_hierarchy", "qualifications"}
    
    if field_name in list_fields:
        if isinstance(value, list):
            # Check if list contains dicts (LLM returned structured data)
            result = []
            for item in value:
                if isinstance(item, dict):
                    # Handle structured dict like {"duty": "...", "percent": 30}
                    if "duty" in item:
                        duty = item.get("duty", "")
                        percent = item.get("percent", item.get("percentage", ""))
                        if percent:
                            result.append(f"{duty} ({percent}%)")
                        else:
                            result.append(str(duty))
                    else:
                        # Generic dict - convert keys/values to strings
                        for k, v in item.items():
                            if isinstance(v, (int, float)):
                                result.append(f"{k} ({v}%)")
                            else:
                                result.append(f"{k}: {v}")
                elif isinstance(item, str):
                    result.append(item)
                else:
                    result.append(str(item))
            return result
        elif isinstance(value, dict):
            # Convert dict like {"duty": 30, "other": 70} to ["duty (30%)", "other (70%)"]
            return [f"{k} ({v}%)" if isinstance(v, (int, float)) else f"{k}: {v}" 
                    for k, v in value.items()]
        elif isinstance(value, str):
            # Split string by common delimiters
            import re
            items = re.split(r'[;,]|\band\b', value)
            return [item.strip() for item in items if item.strip()]
    
    return value


def _apply_field_value(
    interview_data: InterviewData,
    field_name: str,
    value: Any,
    raw_input: str,
    needs_confirmation: bool,
) -> bool:
    """
    Apply a value directly to an interview field.
    
    Args:
        interview_data: The InterviewData instance to update
        field_name: Name of the field to set
        value: Value to set (already normalized)
        raw_input: Original user input text
        needs_confirmation: Whether this needs user confirmation
        
    Returns:
        True if successful, False if field doesn't exist
    """
    if not hasattr(interview_data, field_name):
        return False
    
    element: InterviewElement = getattr(interview_data, field_name)
    element.set_value(
        value=value,
        raw_input=raw_input,
        needs_confirmation=needs_confirmation,
    )
    return True


def _get_or_create_interview_data(state: AgentState) -> InterviewData:
    """
    Retrieve existing InterviewData from state or create new instance.

    Args:
        state: Current agent state

    Returns:
        InterviewData instance (deserialized from state or new)
    """
    interview_dict = state.get("interview_data")
    if interview_dict:
        return InterviewData.model_validate(interview_dict)
    return InterviewData()


def _apply_field_mapping(
    interview_data: InterviewData,
    field_name: str,
    extracted_value: str,
    parsed_value: Any,
    raw_input: str,
    needs_confirmation: bool,
) -> tuple[bool, str | None]:
    """
    Apply a single field mapping to the interview data.

    Args:
        interview_data: The InterviewData instance to update
        field_name: Name of the field to set
        extracted_value: Raw extracted text
        parsed_value: Structured/parsed value
        raw_input: Original user input text
        needs_confirmation: Whether this needs user confirmation

    Returns:
        Tuple of (success, validation_error_message or None)
    """
    if not hasattr(interview_data, field_name):
        return False, None

    # Validate if this field requires validation
    if field_name in VALIDATED_FIELDS:
        validator = VALIDATED_FIELDS[field_name]
        is_valid, error_message = validator(str(parsed_value) if parsed_value else extracted_value)
        if not is_valid:
            return False, error_message

    # Normalize the value to match expected field type
    normalized_value = _normalize_field_value(field_name, parsed_value)
    
    # Use _apply_field_value to ensure field aliasing is handled
    _apply_field_value(interview_data, field_name, normalized_value, raw_input, needs_confirmation)
    
    return True, None


def _build_summary_message(
    mapped_fields: list[dict[str, Any]],
    needs_confirmation: list[str],
) -> str:
    """
    Build a human-friendly summary of mapped answers.

    Args:
        mapped_fields: List of field mappings that were applied
        needs_confirmation: List of field names needing confirmation

    Returns:
        Summary message for the user
    """
    if not mapped_fields:
        return "I wasn't able to extract any field values from that. Could you provide more specific information?"

    # Import here to avoid circular dependency
    from src.utils.personality import get_acknowledgment
    lines = [get_acknowledgment()]
    for mapping in mapped_fields:
        field_name = mapping["field_name"]
        value = mapping["parsed_value"]
        
        # Get friendly field name from INTAKE_FIELDS
        field_def = INTAKE_FIELDS.get(field_name)
        friendly_name = field_name.replace("_", " ").title()
        if field_def:
            # Use first part of prompt as friendly name if available
            friendly_name = field_name.replace("_", " ").title()

        # Format value for display
        if isinstance(value, list):
            value_str = ", ".join(str(v) for v in value)
        elif isinstance(value, dict):
            value_str = "; ".join(f"{k}: {v}" for k, v in value.items())
        elif isinstance(value, bool):
            value_str = "Yes" if value else "No"
        else:
            value_str = str(value)

        lines.append(f"  • **{friendly_name}**: {value_str}")

    if needs_confirmation:
        lines.append("")
        lines.append("I'd like to confirm a couple of things:")
        for field_name in needs_confirmation:
            lines.append(f"  - Is the **{field_name.replace('_', ' ')}** correct?")

    return "\n".join(lines)


def _calculate_missing_fields(
    interview_data: InterviewData,
    is_supervisor: bool | None,
) -> list[str]:
    """
    Calculate which fields are still missing.

    For supervisory positions, also includes conditional supervisory fields
    that should be offered (even though they're technically optional).

    Args:
        interview_data: Current interview data
        is_supervisor: Whether position is supervisory (affects required fields)

    Returns:
        List of field names that still need to be collected
    """
    sequence = get_intake_sequence(is_supervisor)
    
    # Required fields must be collected
    required_fields = [
        name for name in sequence
        if INTAKE_FIELDS.get(name, None) and INTAKE_FIELDS[name].required
    ]
    missing = interview_data.get_unset_required_fields(required_fields)
    
    # For supervisory positions, also offer the optional supervisory fields
    if is_supervisor:
        for name in sequence:
            field = INTAKE_FIELDS.get(name)
            if field and not field.required and field.conditional:
                # Check if this field's condition is met
                if field.conditional.depends_on == "is_supervisor" and field.conditional.value is True:
                    # Offer this field if not already set
                    if hasattr(interview_data, name) and not getattr(interview_data, name).is_set:
                        if name not in missing:
                            missing.append(name)
    
    return missing


def _get_next_field_to_ask(
    interview_data: InterviewData,
    missing_fields: list[str],
) -> str | None:
    """
    Determine the next field to ask about based on sequence.

    Args:
        interview_data: Current interview data
        missing_fields: List of missing field names

    Returns:
        Next field name to ask, or None if all fields collected
    """
    # Follow the defined sequence
    sequence = BASE_INTAKE_SEQUENCE + SUPERVISORY_ADDITIONAL
    for field_name in sequence:
        if field_name in missing_fields:
            return field_name
    return None


def _handle_confirmation(
    interview_data: InterviewData,
    field_name: str,
    confirmed: bool,
) -> str:
    """
    Handle user confirmation or rejection of a field value.

    Args:
        interview_data: Current interview data
        field_name: Field being confirmed/rejected
        confirmed: Whether user confirmed the value

    Returns:
        Response message
    """
    if not hasattr(interview_data, field_name):
        return f"I don't have a field called '{field_name}' to confirm."

    element: InterviewElement = getattr(interview_data, field_name)

    if confirmed:
        element.confirm()
        # Import here to avoid circular dependency
        from src.utils.personality import get_confirmation_success
        return f"{get_confirmation_success()} I've confirmed the **{field_name.replace('_', ' ')}**."
    else:
        # Clear the value so we can re-ask
        element.clear()
        return f"No problem. Let's try again for the **{field_name.replace('_', ' ')}**."


@traced_node
def map_answers_node(state: AgentState) -> dict:
    """
    Map extracted field values to interview data.

    This node:
    1. Retrieves field mappings from intent classification (if available)
    2. Falls back to direct assignment for current_field when no LLM mappings
    3. Applies values to InterviewData with metadata
    4. Handles confirmation of uncertain extractions
    5. Updates missing_fields list
    6. Builds summary response for user

    Args:
        state: Current agent state with _field_mappings from intent classification

    Returns:
        State update with updated interview_data, missing_fields, and message
    """
    try:
        return _map_answers_impl(state)
    except Exception as e:
        # Unexpected error - route to error_handler
        logger.error(f"Unexpected error in map_answers_node: {e}", exc_info=True)
        return {
            "last_error": f"map_answers: {type(e).__name__}: {str(e)}",
            "messages": [AIMessage(content="I had trouble processing that information. Could you try again?")],
        }


def _map_answers_impl(state: AgentState) -> dict:
    """Implementation of map_answers_node (extracted for error handling wrapper)."""
    # Get or create interview data
    interview_data = _get_or_create_interview_data(state)

    # Get field mappings from intent classification
    field_mappings = state.get("_field_mappings", [])
    intent = state.get("last_intent", "")
    
    # Track what we mapped
    mapped_fields: list[dict[str, Any]] = []
    fields_needing_confirmation: list[str] = []

    # Handle confirmation intent
    if intent == "confirm":
        pending_confirmation = state.get("fields_needing_confirmation", [])
        if pending_confirmation:
            # Confirm the first pending field
            field_to_confirm = pending_confirmation[0]
            message = _handle_confirmation(interview_data, field_to_confirm, confirmed=True)
            
            # Remove from pending
            remaining_confirmation = pending_confirmation[1:]
            
            # ALSO process any field_mappings provided with the confirmation
            # (User might say "yes, and the series is 0343")
            additional_messages = []
            if field_mappings:
                for mapping in field_mappings:
                    field_name = mapping.get("field_name", "")
                    # Skip if it's the field we just confirmed
                    if field_name == field_to_confirm:
                        continue
                    parsed_value = mapping.get("parsed_value")
                    raw_input = mapping.get("raw_input", "")
                    needs_confirmation = mapping.get("needs_confirmation", False)
                    
                    if field_name and parsed_value is not None:
                        # Normalize value for storage
                        normalized_value = _normalize_field_value(field_name, parsed_value)
                        _apply_field_value(interview_data, field_name, normalized_value, raw_input, needs_confirmation)
                        mapped_fields.append({
                            "field_name": field_name,
                            "value": normalized_value,
                            "needs_confirmation": needs_confirmation,
                        })
                        if needs_confirmation:
                            remaining_confirmation.append(field_name)
            
            # Calculate missing fields
            is_supervisor = None
            if interview_data.is_supervisor.is_set:
                is_supervisor = interview_data.is_supervisor.value
            missing_fields = _calculate_missing_fields(interview_data, is_supervisor)
            
            # Build combined message
            if mapped_fields:
                additional_summary = _build_summary_message(mapped_fields, [])
                message = f"{message}\n\n{additional_summary}"
            
            return {
                "interview_data": interview_data.model_dump(),
                "fields_needing_confirmation": remaining_confirmation,
                "missing_fields": missing_fields,
                "messages": [AIMessage(content=message)],
            }

    # Handle rejection intent
    if intent == "reject":
        pending_confirmation = state.get("fields_needing_confirmation", [])
        if pending_confirmation:
            # Reject the first pending field
            field_to_reject = pending_confirmation[0]
            message = _handle_confirmation(interview_data, field_to_reject, confirmed=False)

            # Remove from pending (field is now cleared and needs re-asking)
            remaining_confirmation = pending_confirmation[1:]

            # Calculate missing fields (now includes the rejected field)
            is_supervisor = None
            if interview_data.is_supervisor.is_set:
                is_supervisor = interview_data.is_supervisor.value
            missing_fields = _calculate_missing_fields(interview_data, is_supervisor)

            return {
                "interview_data": interview_data.model_dump(),
                "fields_needing_confirmation": remaining_confirmation,
                "missing_fields": missing_fields,
                "messages": [AIMessage(content=message)],
            }

        # Safety net: if "reject" during interview with no pending confirmations,
        # the user is likely answering a boolean field with "no".
        # Check if the current field is boolean and apply the value.
        from src.config.intake_fields import INTAKE_FIELDS
        current_field = state.get("current_field", "")
        field_config = INTAKE_FIELDS.get(current_field, {})
        if (
            current_field
            and field_config.get("field_type") == "boolean"
            and hasattr(interview_data, current_field)
        ):
            element: InterviewElement = getattr(interview_data, current_field)
            if not element.is_set:
                element.set_value(value=False, raw_input="no", needs_confirmation=False)
                element.confirm()
                is_supervisor = None
                if interview_data.is_supervisor.is_set:
                    is_supervisor = interview_data.is_supervisor.value
                missing_fields = _calculate_missing_fields(interview_data, is_supervisor)
                return {
                    "interview_data": interview_data.model_dump(),
                    "missing_fields": missing_fields,
                    "messages": [AIMessage(content=f"Got it — **{current_field.replace('_', ' ')}** set to: No")],
                }

    # Handle modify_answer intent
    if intent == "modify_answer":
        modification = state.get("_modification", {})
        if modification:
            field_name = modification.get("field")
            new_value = modification.get("new_value")
            if field_name and new_value:
                # Validate if this field requires validation
                if field_name in VALIDATED_FIELDS:
                    validator = VALIDATED_FIELDS[field_name]
                    is_valid, error_message = validator(str(new_value))
                    if not is_valid:
                        # Return validation error - let prepare_next show it
                        return {
                            "validation_error": error_message,
                            "current_field": field_name,
                            "messages": [AIMessage(content=f"Hmm, that doesn't look quite right. {error_message}")],
                        }
                
                # Clear the old value and set new one
                if hasattr(interview_data, field_name):
                    element: InterviewElement = getattr(interview_data, field_name)
                    element.set_value(
                        value=new_value,
                        raw_input=f"User modified to: {new_value}",
                        needs_confirmation=False,
                    )
                    element.confirm()  # User explicitly changed it, so it's confirmed
                    
                    message = f"Updated **{field_name.replace('_', ' ')}** to: {new_value}"
                    
                    # Calculate missing fields
                    is_supervisor = None
                    if interview_data.is_supervisor.is_set:
                        is_supervisor = interview_data.is_supervisor.value
                    missing_fields = _calculate_missing_fields(interview_data, is_supervisor)
                    
                    return {
                        "interview_data": interview_data.model_dump(),
                        "missing_fields": missing_fields,
                        "validation_error": None,  # Clear any previous validation error
                        "messages": [AIMessage(content=message)],
                    }

    # Apply any field mappings from provide_information intent
    validation_errors = []  # Collect validation errors for fields
    
    # =========================================================================
    # NO HEURISTIC FALLBACK POLICY (see AGENTS.MD, ADR-005, ADR-006)
    # =========================================================================
    # If the LLM didn't return field_mappings, we do NOT fall back to dumping
    # the entire user message into current_field. That's a heuristic bypass
    # that creates false confidence and masks prompt/extraction bugs.
    # 
    # The LLM MUST extract fields. If field_mappings is empty, it means:
    # 1. The user didn't provide information (different intent), OR
    # 2. The prompt needs improvement to extract the fields
    #
    # DO NOT ADD FALLBACK LOGIC HERE.
    # =========================================================================
    
    if not field_mappings:
        # No fields to map - this is fine, user may have asked a question
        # or confirmed something. Return without modifications.
        is_supervisor = None
        if interview_data.is_supervisor.is_set:
            is_supervisor = interview_data.is_supervisor.value
        missing_fields = _calculate_missing_fields(interview_data, is_supervisor)
        
        return {
            "interview_data": interview_data.model_dump(),
            "missing_fields": missing_fields,
            "messages": [AIMessage(content="I didn't catch any field values there. Could you provide specific information for the interview?")],
        }
    
    for mapping in field_mappings:
        field_name = mapping.get("field_name")
        extracted_value = mapping.get("extracted_value", "")
        parsed_value = mapping.get("parsed_value")
        raw_input = mapping.get("raw_input", "")
        needs_confirmation = mapping.get("needs_confirmation", False)

        success, validation_error = _apply_field_mapping(
            interview_data,
            field_name,
            extracted_value,
            parsed_value,
            raw_input,
            needs_confirmation,
        )

        if success:
            mapped_fields.append(mapping)
            if needs_confirmation:
                fields_needing_confirmation.append(field_name)
        elif validation_error:
            validation_errors.append((field_name, validation_error))

    # Check if is_supervisor was just set and expand required fields
    is_supervisor = None
    if interview_data.is_supervisor.is_set:
        is_supervisor = interview_data.is_supervisor.value

    # Calculate missing fields based on current is_supervisor value
    missing_fields = _calculate_missing_fields(interview_data, is_supervisor)

    # Get existing confirmation needs
    existing_confirmation = state.get("fields_needing_confirmation", [])
    
    # Fields that were mapped with needs_confirmation=false should be REMOVED from pending
    # (user provided a definitive answer, no need to re-confirm)
    fields_to_remove = set()
    for mapping in mapped_fields:
        if not mapping.get("needs_confirmation", False):
            fields_to_remove.add(mapping.get("field_name"))
    
    # Update confirmation list: add new ones, remove confirmed ones
    all_needing_confirmation = [
        f for f in existing_confirmation if f not in fields_to_remove
    ]
    for f in fields_needing_confirmation:
        if f not in all_needing_confirmation:
            all_needing_confirmation.append(f)

    # Build summary message
    summary = _build_summary_message(mapped_fields, all_needing_confirmation)
    
    # If there were validation errors, append them to the message
    validation_error_str = None
    if validation_errors:
        # Use the first validation error for the state field
        field_name, error_msg = validation_errors[0]
        validation_error_str = error_msg
        summary += f"\n\n⚠️ {error_msg}"

    return {
        "interview_data": interview_data.model_dump(),
        "missing_fields": missing_fields,
        "fields_needing_confirmation": all_needing_confirmation,
        "validation_error": validation_error_str,
        "messages": [AIMessage(content=summary)],
        # Clear the temporary field mappings
        "_field_mappings": None,
        "_modification": None,
    }
