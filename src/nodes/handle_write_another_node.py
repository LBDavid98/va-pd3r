"""Handle write another node - processes user response to "write another PD?" prompt."""

from langchain_core.messages import AIMessage

from src.models.state import AgentState
from src.utils.llm import traced_node


@traced_node
def handle_write_another_node(state: AgentState) -> dict:
    """
    Handle the user's response to "Would you like to write another PD?"

    Uses structured IntentClassification from LLM - the LLM has already
    determined the user's intent with full context.

    Intent mapping:
    - confirm → wants_another = True
    - reject → wants_another = False
    - request_export with format="none" → wants_another = False (user said "done", "no thanks")

    Args:
        state: Current agent state with intent_classification

    Returns:
        State update with wants_another flag set
    """
    intent = state.get("last_intent", "")
    classification = state.get("intent_classification")

    # Primary check: Use structured intent from LLM
    if intent == "confirm":
        return {
            "wants_another": True,
            "is_restart": True,
        }

    if intent == "reject":
        return {
            "wants_another": False,
        }

    # Check for request_export with format="none" (LLM classified "done", "no thanks", etc.)
    # This is how the prompt instructs the LLM to classify polite declines
    if intent == "request_export":
        # First try the structured classification object
        if classification and hasattr(classification, "export_request"):
            export_request = classification.export_request
            if export_request and getattr(export_request, "format", None) == "none":
                return {
                    "wants_another": False,
                }
        # Fallback: check the serialized _export_request dict
        export_dict = state.get("_export_request")
        if export_dict and export_dict.get("format") == "none":
            return {
                "wants_another": False,
            }

    # For any other intent, ask for clarification
    clarification = (
        "I'm not sure if you want to write another PD. "
        "Just say 'yes' to start a new one, or 'no' to finish up."
    )
    return {
        "next_prompt": clarification,
        "messages": [AIMessage(content=clarification)],
    }
