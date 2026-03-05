"""End conversation node - graceful exit from the agent."""

from langchain_core.messages import AIMessage

from src.models.state import AgentState
from src.utils.llm import traced_node


FAREWELL_MESSAGES = [
    "Thanks for using Pete! Goodbye.",
    "Take care! Feel free to come back anytime you need help with a PD.",
    "Goodbye! Best of luck with your position description.",
]

WRITE_ANOTHER_PROMPT = (
    "Your position description is complete! "
    "Would you like to write another PD?"
)


@traced_node
def end_conversation_node(state: AgentState) -> dict:
    """
    End the conversation gracefully, with option to write another PD.

    Flow:
    1. First call (wants_another=None): Ask if user wants another PD,
       route to user_input for response
    2. After user responds and handle_write_another sets wants_another:
       - wants_another=True: Route to init (via route_after_end_conversation)
       - wants_another=False: Send farewell, truly end

    Args:
        state: Current agent state

    Returns:
        State update with appropriate message and phase
    """
    wants_another = state.get("wants_another")

    # If we haven't asked yet, ask and route to user_input
    if wants_another is None:
        return {
            "phase": "complete",
            "should_end": False,
            "next_prompt": WRITE_ANOTHER_PROMPT,
            "messages": [AIMessage(content=WRITE_ANOTHER_PROMPT)],
        }

    # User has responded - if they want another, route will handle restart
    if wants_another:
        # Routing will send to init
        return {
            "phase": "complete",
            "should_end": False,
            "is_restart": True,
            "next_prompt": "",
            "messages": [],
        }

    # User said no - send farewell and truly end
    farewell = FAREWELL_MESSAGES[0]
    return {
        "phase": "complete",
        "should_end": True,
        "next_prompt": "",
        "messages": [AIMessage(content=farewell)],
    }
