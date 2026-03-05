"""Custom exceptions for PD3r (Pete).

This module defines a hierarchy of exceptions for error handling and recovery.
All PD3r exceptions inherit from PD3rException for easy catching.
"""

from typing import Any


class PD3rException(Exception):
    """Base exception for all PD3r errors.
    
    All custom exceptions in PD3r should inherit from this class
    to enable unified error handling and logging.
    """
    
    def __init__(self, message: str, context: dict[str, Any] | None = None):
        """Initialize the exception.
        
        Args:
            message: Human-readable error description
            context: Optional dict with debugging context
        """
        super().__init__(message)
        self.message = message
        self.context = context or {}
    
    def __str__(self) -> str:
        if self.context:
            return f"{self.message} | Context: {self.context}"
        return self.message


# =============================================================================
# LLM Exceptions
# =============================================================================

class LLMException(PD3rException):
    """Base exception for LLM-related errors."""
    pass


class LLMConnectionError(LLMException):
    """Failed to connect to LLM API.
    
    This typically indicates network issues, invalid API keys,
    or the API service being unavailable.
    """
    
    user_message = (
        "I'm having trouble connecting to my AI backend right now. "
        "Let me try again in a moment..."
    )


class LLMRateLimitError(LLMException):
    """LLM API rate limit exceeded.
    
    Triggered when too many requests are made in a short period.
    The caller should implement exponential backoff.
    """
    
    user_message = (
        "I'm getting a bit overwhelmed with requests. "
        "Give me a moment to catch up..."
    )


class LLMResponseError(LLMException):
    """Invalid or unexpected response from LLM.
    
    This includes malformed JSON, unexpected structure,
    or responses that don't match the expected schema.
    """
    
    user_message = (
        "I got a confusing response from my AI backend. "
        "Let me try that again..."
    )


class LLMTimeoutError(LLMException):
    """LLM request timed out.
    
    The request took too long to complete.
    Consider breaking down complex prompts or increasing timeout.
    """
    
    user_message = (
        "That took longer than expected. "
        "Let me try a simpler approach..."
    )


class LLMRetryExhaustedError(LLMException):
    """All retry attempts exhausted.
    
    The operation failed after all configured retry attempts.
    """
    
    def __init__(
        self, 
        message: str, 
        attempts: int,
        last_error: Exception | None = None,
        context: dict[str, Any] | None = None,
    ):
        super().__init__(message, context)
        self.attempts = attempts
        self.last_error = last_error
    
    user_message = (
        "I've tried several times but keep running into issues. "
        "Would you like me to try a different approach, or should we skip this step?"
    )


# =============================================================================
# Configuration Exceptions
# =============================================================================

class ConfigurationError(PD3rException):
    """Raised when required configuration is missing or invalid.
    
    This exception is used for fail-fast behavior when critical
    configuration (like API keys) is missing. Unlike runtime errors,
    configuration errors should be fixed before running the agent.
    
    Common causes:
    - Missing OPENAI_API_KEY environment variable
    - Invalid configuration file
    - Missing required dependencies
    """
    
    user_message = (
        "There's a configuration issue that needs to be fixed. "
        "Please check that all required environment variables are set."
    )


# =============================================================================
# Validation Exceptions
# =============================================================================

class ValidationException(PD3rException):
    """Base exception for validation errors."""
    pass


class FieldValidationError(ValidationException):
    """Field value failed validation.
    
    Used when user input doesn't meet field requirements
    (e.g., invalid series code, invalid grade).
    """
    
    def __init__(
        self,
        field_name: str,
        provided_value: Any,
        error_message: str,
        context: dict[str, Any] | None = None,
    ):
        ctx = context or {}
        ctx.update({
            "field_name": field_name,
            "provided_value": provided_value,
        })
        super().__init__(error_message, ctx)
        self.field_name = field_name
        self.provided_value = provided_value
        self.error_message = error_message
    
    @property
    def user_message(self) -> str:
        """Generate user-friendly validation error message."""
        return f"Hmm, that doesn't look quite right. {self.error_message}"


# =============================================================================
# State Exceptions
# =============================================================================

class StateException(PD3rException):
    """Base exception for state-related errors."""
    pass


class CheckpointerError(StateException):
    """Error saving or loading checkpoint.
    
    This indicates issues with state persistence.
    """
    
    user_message = (
        "I had trouble saving our progress. "
        "Don't worry, we can continue, but you might need to re-enter some information if we get disconnected."
    )


class InvalidStateError(StateException):
    """State is in an unexpected or invalid condition.
    
    This indicates a bug in the graph logic or corrupted state.
    """
    
    user_message = (
        "I seem to have gotten a bit confused. "
        "Let me reset and we can start fresh on this section."
    )


class MissingStateFieldError(StateException):
    """Required state field is missing.
    
    A field that should have been set by a previous node is missing.
    """
    
    def __init__(
        self,
        field_name: str,
        expected_phase: str | None = None,
        context: dict[str, Any] | None = None,
    ):
        msg = f"Missing required state field: {field_name}"
        if expected_phase:
            msg += f" (expected after {expected_phase} phase)"
        ctx = context or {}
        ctx["field_name"] = field_name
        super().__init__(msg, ctx)
        self.field_name = field_name


# =============================================================================
# Node Exceptions  
# =============================================================================

class NodeException(PD3rException):
    """Base exception for node execution errors."""
    
    def __init__(
        self,
        node_name: str,
        message: str,
        context: dict[str, Any] | None = None,
    ):
        ctx = context or {}
        ctx["node_name"] = node_name
        super().__init__(message, ctx)
        self.node_name = node_name


class NodeExecutionError(NodeException):
    """Error during node execution.
    
    A non-recoverable error occurred during node execution.
    """
    
    user_message = (
        "I ran into an unexpected issue. "
        "Let me try to recover..."
    )


# =============================================================================
# Export Exceptions
# =============================================================================

class ExportException(PD3rException):
    """Base exception for export errors."""
    pass


class ExportFormatError(ExportException):
    """Invalid or unsupported export format requested."""
    
    user_message = (
        "I don't recognize that export format. "
        "I can export to Word (.docx) or Markdown (.md)."
    )


class ExportWriteError(ExportException):
    """Failed to write export file.
    
    Could be permissions, disk space, or path issues.
    """
    
    user_message = (
        "I had trouble saving the file. "
        "Please check that you have write access to the output folder."
    )


# =============================================================================
# Knowledge Base / RAG Exceptions
# =============================================================================

class KnowledgeBaseException(PD3rException):
    """Base exception for knowledge base errors."""
    pass


class VectorStoreError(KnowledgeBaseException):
    """Error accessing or querying the vector store."""
    
    user_message = (
        "I'm having trouble accessing my knowledge base. "
        "I'll answer based on general knowledge instead."
    )


class DocumentNotFoundError(KnowledgeBaseException):
    """Referenced document not found in knowledge base."""
    pass


# =============================================================================
# Utility Functions
# =============================================================================

def get_user_message(exception: Exception) -> str:
    """Get user-friendly message for any exception.
    
    Args:
        exception: The exception to get a message for
        
    Returns:
        User-friendly error message string
    """
    # Check if it's a PD3r exception with user_message
    if hasattr(exception, "user_message"):
        msg = exception.user_message
        # Handle both property and attribute
        return msg() if callable(msg) else msg
    
    # Generic fallback for unknown exceptions
    return (
        "Oops, something unexpected happened. "
        "Let me try to recover and continue."
    )


def is_retryable(exception: Exception) -> bool:
    """Check if an exception is retryable.
    
    Args:
        exception: The exception to check
        
    Returns:
        True if the operation should be retried
    """
    retryable_types = (
        LLMConnectionError,
        LLMRateLimitError,
        LLMTimeoutError,
    )
    return isinstance(exception, retryable_types)
