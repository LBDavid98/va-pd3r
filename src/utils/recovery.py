"""Error recovery utilities for PD3r nodes.

This module provides utilities for graceful error handling within nodes,
including user-friendly recovery messages and error state management.
"""

from typing import Any

from langchain_core.messages import AIMessage

from src.exceptions import (
    LLMException,
    LLMRetryExhaustedError,
    NodeException,
    PD3rException,
    get_user_message,
)
from src.models.state import AgentState


def create_recovery_response(
    exception: Exception,
    node_name: str,
    state: AgentState,
    fallback_message: str | None = None,
) -> dict[str, Any]:
    """
    Create a recovery response after an error in a node.
    
    This function generates a user-friendly response and records
    the error in state for potential debugging/recovery.
    
    Args:
        exception: The exception that occurred
        node_name: Name of the node where error occurred
        state: Current agent state
        fallback_message: Optional custom fallback message
        
    Returns:
        State update dict with error message and last_error field
    """
    # Get user-friendly message
    user_message = fallback_message or get_user_message(exception)
    
    # Record error details (sanitized) for debugging
    error_detail = f"{node_name}: {type(exception).__name__}: {str(exception)[:200]}"
    
    return {
        "last_error": error_detail,
        "messages": [AIMessage(content=user_message)],
    }


def handle_llm_error_in_node(
    exception: Exception,
    node_name: str,
    state: AgentState,
    operation_description: str = "process that",
) -> dict[str, Any]:
    """
    Handle an LLM-related error within a node.
    
    Provides specific handling for different LLM error types with
    appropriate user messaging.
    
    Args:
        exception: The LLM exception that occurred
        node_name: Name of the node where error occurred
        state: Current agent state
        operation_description: Description of what was being attempted
        
    Returns:
        State update dict with appropriate recovery response
    """
    if isinstance(exception, LLMRetryExhaustedError):
        message = (
            f"I've tried several times to {operation_description}, but I keep running into issues. "
            "Let me try a different approach. What would you like to do?"
        )
    elif isinstance(exception, LLMException):
        message = get_user_message(exception)
    else:
        message = (
            f"I ran into an unexpected issue while trying to {operation_description}. "
            "Let me try again..."
        )
    
    return create_recovery_response(
        exception=exception,
        node_name=node_name,
        state=state,
        fallback_message=message,
    )


def wrap_node_with_recovery(node_func):
    """
    Decorator that wraps a node function with error recovery.
    
    If the node raises a PD3rException, this decorator catches it
    and returns a graceful recovery response instead of crashing.
    
    Usage:
        @wrap_node_with_recovery
        def my_node(state: AgentState) -> dict:
            # ... node logic
            pass
    
    Args:
        node_func: The node function to wrap
        
    Returns:
        Wrapped function with error recovery
    """
    def wrapped(state: AgentState) -> dict:
        try:
            return node_func(state)
        except PD3rException as e:
            node_name = node_func.__name__
            return create_recovery_response(
                exception=e,
                node_name=node_name,
                state=state,
            )
        except Exception as e:
            # For unexpected errors, log but don't crash
            node_name = node_func.__name__
            return create_recovery_response(
                exception=e,
                node_name=node_name,
                state=state,
                fallback_message=(
                    "Oops, something unexpected happened. "
                    "Let me try to recover and continue."
                ),
            )
    
    # Preserve function metadata
    wrapped.__name__ = node_func.__name__
    wrapped.__doc__ = node_func.__doc__
    
    return wrapped


async def wrap_async_node_with_recovery(node_func):
    """
    Async version of wrap_node_with_recovery.
    
    Args:
        node_func: The async node function to wrap
        
    Returns:
        Wrapped async function with error recovery
    """
    async def wrapped(state: AgentState) -> dict:
        try:
            return await node_func(state)
        except PD3rException as e:
            node_name = node_func.__name__
            return create_recovery_response(
                exception=e,
                node_name=node_name,
                state=state,
            )
        except Exception as e:
            node_name = node_func.__name__
            return create_recovery_response(
                exception=e,
                node_name=node_name,
                state=state,
                fallback_message=(
                    "Oops, something unexpected happened. "
                    "Let me try to recover and continue."
                ),
            )
    
    wrapped.__name__ = node_func.__name__
    wrapped.__doc__ = node_func.__doc__
    
    return wrapped


def safe_state_access(
    state: AgentState,
    key: str,
    default: Any = None,
    error_on_missing: bool = False,
) -> Any:
    """
    Safely access a state field with optional error handling.
    
    Args:
        state: Agent state dict
        key: Key to access
        default: Default value if key missing
        error_on_missing: If True, raise MissingStateFieldError
        
    Returns:
        Value from state or default
        
    Raises:
        MissingStateFieldError: If error_on_missing=True and key is missing
    """
    value = state.get(key)
    
    if value is None and error_on_missing:
        from src.exceptions import MissingStateFieldError
        raise MissingStateFieldError(field_name=key)
    
    return value if value is not None else default
