"""User input node - pauses execution to collect user input via interrupt."""

from langchain_core.messages import HumanMessage
from langgraph.types import interrupt

from src.models.state import AgentState
from src.utils.llm import traced_node


@traced_node
def user_input_node(state: AgentState) -> dict:
    """
    Collect user input via LangGraph interrupt.

    Pauses graph execution and returns control to the caller.
    When resumed with Command(resume=<user_input>), execution continues
    with the user's response.

    Args:
        state: Current agent state containing next_prompt

    Returns:
        State update with user input added to messages
    """
    # Interrupt execution and wait for user input
    # The interrupt payload provides context to the caller
    user_response = interrupt(
        {
            "prompt": state.get("next_prompt", ""),
            "phase": state.get("phase", "init"),
            "missing_fields": state.get("missing_fields", []),
            "current_field": state.get("current_field"),
        }
    )

    # When resumed, user_response contains the user's input
    return {
        "messages": [HumanMessage(content=user_response)],
    }
