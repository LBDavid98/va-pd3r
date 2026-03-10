"""Reprompt node - generates phase-appropriate clarification when intent is unrecognized.

When the LLM classifies a user message with an intent that doesn't map to a
clear next action, the graph routes here instead of silently looping back to
user_input with no AI response. This ensures the user always gets feedback.
"""

from langchain_core.messages import AIMessage

from src.models.state import AgentState
from src.utils.llm import traced_node


@traced_node
def reprompt_node(state: AgentState) -> dict:
    """Generate a phase-appropriate clarification message.

    Instead of silently re-interrupting with a stale prompt, this node
    tells the user what it expects and how to proceed.

    Args:
        state: Current agent state

    Returns:
        State update with clarification message and next_prompt
    """
    phase = state.get("phase", "init")

    if phase == "init":
        prompt = (
            "I'm not sure I understood that. Would you like me to help you "
            "write a position description? Just say **yes** to get started, "
            "or ask me a question about the process."
        )
    elif phase == "interview":
        current_field = state.get("current_field")
        if current_field:
            from src.config.intake_fields import INTAKE_FIELDS

            field_def = INTAKE_FIELDS.get(current_field)
            guidance = field_def.user_guidance if field_def else ""
            prompt = (
                f"I wasn't able to capture your response for that question. "
                f"Could you try rephrasing? {guidance}"
            ).strip()
        else:
            prompt = (
                "I didn't quite catch that. Could you rephrase your answer? "
                "You can also ask me a question if something is unclear."
            )
    elif phase == "requirements":
        prompt = (
            "I need your confirmation before I can start drafting. "
            "Say **yes** to approve the summary above, or tell me what needs to change."
        )
    elif phase == "drafting":
        current_element = state.get("current_element_name", "the current section")
        prompt = (
            f"I need your feedback on **{current_element}**. "
            "Say **approve** to accept it, or describe the changes you'd like."
        )
    elif phase == "review":
        prompt = (
            "Please review the complete document above. "
            "Say **approve** to finalize, or tell me which section to revise."
        )
    elif phase == "complete":
        prompt = (
            "Would you like to export the document? "
            "Choose **word** or **markdown**, or say **done** if you're finished."
        )
    else:
        prompt = "I didn't understand that. Could you try again?"

    return {
        "next_prompt": prompt,
        "messages": [AIMessage(content=prompt)],
    }
