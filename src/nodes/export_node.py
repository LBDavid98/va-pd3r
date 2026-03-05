"""Export document node for position description export.

Handles exporting the finalized position description to
markdown or Word document format.

Includes error handling that routes to error_handler on critical failures.
"""

import logging

from langchain_core.messages import AIMessage

from src.models.state import AgentState
from src.tools.export_tools import export_to_markdown, export_to_word
from src.utils.llm import traced_node

logger = logging.getLogger(__name__)


def _format_error(error: Exception) -> str:
    """Format an exception for the error handler.
    
    Error format: "node_name: ErrorType: message"
    """
    return f"export_document: {type(error).__name__}: {str(error)}"


@traced_node
def export_document_node(state: AgentState) -> dict:
    """
    Handle document export based on user's format choice.

    Exports the finalized position description to the requested
    format (markdown or Word), or skips export if user said "done".

    Args:
        state: Current agent state with draft_elements, interview_data,
               and the classified intent with export_request

    Returns:
        State update with export result message and next phase
    """
    draft_elements = state.get("draft_elements", [])
    interview_data = state.get("interview_data")
    last_intent_data = state.get("intent_classification")

    # Default export format from raw intent if no structured data
    export_format = _extract_export_format(state)

    if export_format == "none":
        # User doesn't want to export - just confirm and let end_conversation handle "write another?"
        return {
            "messages": [
                AIMessage(
                    content="No problem! Your position description is saved and ready."
                )
            ],
            # Don't set next_prompt - end_conversation will ask "write another?"
        }

    if export_format == "word":
        try:
            export_path = export_to_word(
                draft_elements,
                interview_data,
            )
            return {
                "messages": [
                    AIMessage(
                        content=f"Your position description has been exported to Word format.\n\n"
                        f"📄 **Saved to:** `{export_path}`"
                    )
                ],
                # Don't set next_prompt - end_conversation will ask "write another?"
            }
        except PermissionError as e:
            # Critical error - route to error_handler
            logger.error(f"Permission error exporting to Word: {e}")
            return {
                "last_error": _format_error(e),
                "messages": [AIMessage(content="Export failed due to a permission error.")],
            }
        except OSError as e:
            # Critical error - route to error_handler
            logger.error(f"OS error exporting to Word: {e}")
            return {
                "last_error": _format_error(e),
                "messages": [AIMessage(content="Export failed due to a file system error.")],
            }
        except Exception as e:
            # Non-critical - let user try different format
            logger.warning(f"Error exporting to Word: {e}")
            return {
                "messages": [
                    AIMessage(
                        content=f"Sorry, there was an error exporting to Word: {str(e)}\n\n"
                        "Would you like to try a different format, or say 'done' to skip export?"
                    )
                ],
                "next_prompt": "Try 'markdown' for a different format, or 'done' to skip.",
            }

    if export_format == "markdown":
        try:
            export_path = export_to_markdown(
                draft_elements,
                interview_data,
            )
            return {
                "messages": [
                    AIMessage(
                        content=f"Your position description has been exported to Markdown format.\n\n"
                        f"📄 **Saved to:** `{export_path}`"
                    )
                ],
                # Don't set next_prompt - end_conversation will ask "write another?"
            }
        except PermissionError as e:
            # Critical error - route to error_handler
            logger.error(f"Permission error exporting to Markdown: {e}")
            return {
                "last_error": _format_error(e),
                "messages": [AIMessage(content="Export failed due to a permission error.")],
            }
        except OSError as e:
            # Critical error - route to error_handler
            logger.error(f"OS error exporting to Markdown: {e}")
            return {
                "last_error": _format_error(e),
                "messages": [AIMessage(content="Export failed due to a file system error.")],
            }
        except Exception as e:
            # Non-critical - let user try different format
            logger.warning(f"Error exporting to Markdown: {e}")
            return {
                "messages": [
                    AIMessage(
                        content=f"Sorry, there was an error exporting to Markdown: {str(e)}\n\n"
                        "Would you like to try a different format, or say 'done' to skip export?"
                    )
                ],
                "next_prompt": "Try 'word' for a different format, or 'done' to skip.",
            }

    # Unknown format - ask for clarification
    return {
        "messages": [
            AIMessage(
                content="I didn't understand the export format. Please choose:\n"
                "- **'word'** for a Word document (.docx)\n"
                "- **'markdown'** for a Markdown file (.md)\n"
                "- **'done'** to skip export"
            )
        ],
        "next_prompt": "Choose your export format, or say 'done' to finish.",
    }


def _extract_export_format(state: AgentState) -> str:
    """
    Extract the export format from state.

    Tries to get format from structured intent classification first,
    then falls back to parsing the raw intent string.

    Args:
        state: Current agent state

    Returns:
        Export format string: 'markdown', 'word', 'none', or 'unknown'
    """
    # Try to get from structured intent classification
    intent_data = state.get("intent_classification")
    if intent_data and isinstance(intent_data, dict):
        export_request = intent_data.get("export_request")
        if export_request and isinstance(export_request, dict):
            return export_request.get("format", "unknown")

    # Fall back to parsing raw message
    messages = state.get("messages", [])
    if messages:
        # Get last human message
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "human":
                content = msg.content.lower()
                if any(kw in content for kw in ["word", "docx", ".docx"]):
                    return "word"
                if any(kw in content for kw in ["markdown", "md", ".md"]):
                    return "markdown"
                if any(kw in content for kw in ["done", "skip", "no", "none"]):
                    return "none"
                break

    return "unknown"
