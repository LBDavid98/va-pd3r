"""Error handler node - provides consistent error recovery across the graph.

This node centralizes error handling for all graph nodes, providing:
- User-friendly error messages
- Error state cleanup
- Consistent recovery routing (back to user_input)

Why a centralized error handler?
- Prevents hard crashes from propagating to users
- Provides consistent UX when things go wrong
- Enables debugging by capturing error details before clearing
- Keeps error handling logic DRY across all nodes
"""

import logging
from typing import Any

from langchain_core.messages import AIMessage

from src.models.state import AgentState

logger = logging.getLogger(__name__)


# Error type to user message mapping
ERROR_MESSAGES = {
    "LLMConnectionError": (
        "I'm having trouble connecting to my AI backend right now. "
        "Let's try that again - what were you saying?"
    ),
    "LLMRateLimitError": (
        "I'm getting a bit overwhelmed with requests. "
        "Give me a moment and try again."
    ),
    "LLMResponseError": (
        "I got a confusing response from my AI backend. "
        "Could you repeat that?"
    ),
    "LLMTimeoutError": (
        "That took longer than expected. "
        "Let me try a simpler approach - what were you working on?"
    ),
    "LLMRetryExhaustedError": (
        "I've tried several times but keep running into issues. "
        "Let's continue - what would you like to do?"
    ),
    "ConfigurationError": (
        "There's a configuration issue that needs to be fixed. "
        "Please check that all required environment variables are set."
    ),
    "FieldValidationError": (
        "That value doesn't look quite right. "
        "Could you try entering it again?"
    ),
    "CheckpointerError": (
        "I had trouble saving our progress, but we can continue. "
        "What would you like to do next?"
    ),
}

DEFAULT_ERROR_MESSAGE = (
    "I ran into an unexpected issue. "
    "Let's continue - what would you like to do?"
)


def _extract_error_type(error_string: str) -> str:
    """Extract the error type from the error string.
    
    Error strings are formatted as: "node_name: ErrorType: message"
    
    Args:
        error_string: The error string from state.last_error
        
    Returns:
        The error type name, or empty string if not found
    """
    if not error_string:
        return ""
    
    # Format: "node_name: ErrorType: message"
    parts = error_string.split(": ", 2)
    if len(parts) >= 2:
        return parts[1]
    return ""


def _get_user_message(error_string: str) -> str:
    """Get user-friendly message for an error.
    
    Args:
        error_string: The error string from state.last_error
        
    Returns:
        User-friendly error message
    """
    error_type = _extract_error_type(error_string)
    return ERROR_MESSAGES.get(error_type, DEFAULT_ERROR_MESSAGE)


def error_handler_node(state: AgentState) -> dict[str, Any]:
    """
    Handle errors from other nodes and provide recovery.
    
    This node:
    1. Logs the error details for debugging
    2. Generates a user-friendly recovery message
    3. Clears the error state
    4. Returns control to user_input via next_prompt
    
    Args:
        state: Current agent state with last_error populated
        
    Returns:
        State update clearing error and providing recovery message
    """
    error = state.get("last_error")
    
    if not error:
        # No error to handle - this shouldn't happen but handle gracefully
        logger.warning("error_handler_node called but no last_error in state")
        return {}
    
    # Log the error for debugging
    logger.error(f"Error recovery triggered: {error}")
    
    # Get user-friendly message
    user_message = _get_user_message(error)
    
    # Return state update that clears error and provides recovery message.
    # next_prompt is required so user_input_node has something to interrupt with.
    return {
        "last_error": None,  # Clear the error
        "messages": [AIMessage(content=user_message)],
        "next_prompt": user_message,
    }


def route_after_error(state: AgentState) -> str:
    """
    Route after error handler.
    
    Always routes to user_input to let the user continue.
    
    Args:
        state: Current agent state
        
    Returns:
        Always "user_input"
    """
    return "user_input"
