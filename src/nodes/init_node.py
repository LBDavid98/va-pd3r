"""Init node - initializes conversation and greets user."""

from langchain_core.messages import AIMessage

from src.constants import REQUIRED_FIELDS
from src.models.interview import InterviewData
from src.models.state import AgentState
from src.utils.llm import traced_node


GREETING = (
    "Hi, I'm PD3r, but you can call me Pete. "
    "I help write Federal Position Descriptions. "
    "Would you like me to help you write a PD?"
)

RESTART_GREETING = (
    "Great! Let's write another Position Description. "
    "Would you like me to help you write a PD?"
)


def _build_resume_greeting(state: AgentState) -> str:
    """Build a resume greeting based on saved state."""
    interview_data = state.get("interview_data", {})
    title = interview_data.get("position_title", {}).get("value")
    phase = state.get("phase", "init")
    
    if title:
        return (
            f"Welcome back! You were working on a Position Description for \"{title}\". "
            f"We're currently in the {phase} phase. Ready to continue?"
        )
    return (
        "Welcome back! You have a session in progress. "
        "Ready to continue where we left off?"
    )


@traced_node
def init_node(state: AgentState) -> dict:
    """
    Initialize the conversation.

    Sets up the initial state with:
    - Empty interview data
    - List of required fields to collect
    - Greeting message for the user

    If is_restart is True (user wants to write another PD), resets
    interview state but preserves the session.
    
    If is_resume is True (session restored from checkpoint), shows
    a resume greeting and preserves all existing state.

    Args:
        state: Current agent state (may be empty on first run)

    Returns:
        State updates with initialized fields and greeting
    """
    is_restart = state.get("is_restart", False)
    is_resume = state.get("is_resume", False)
    
    # Resume flow: preserve existing state, just update greeting
    if is_resume:
        greeting = _build_resume_greeting(state)
        return {
            "next_prompt": greeting,
            "messages": [AIMessage(content=greeting)],
            "is_resume": False,  # Clear flag after handling
        }
    
    # New conversation or restart
    interview_data = InterviewData()

    # Choose appropriate greeting
    greeting = RESTART_GREETING if is_restart else GREETING

    return {
        "phase": "init",
        "interview_data": interview_data.model_dump(),
        "missing_fields": list(REQUIRED_FIELDS),
        "fields_needing_confirmation": [],
        "current_field": None,
        "last_intent": None,
        "pending_question": None,
        "fes_evaluation": None,
        "draft_requirements": None,
        "draft_elements": [],
        "current_element_index": 0,
        "current_element_name": None,
        "should_end": False,
        "next_prompt": greeting,
        "messages": [AIMessage(content=greeting)],
        # Reset write another flags
        "wants_another": None,
        "is_restart": False,
        "is_resume": False,
    }
