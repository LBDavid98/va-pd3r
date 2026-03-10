"""Main PD3r workflow graph."""

import logging
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from src.exceptions import CheckpointerError
from src.models.state import AgentState
from src.nodes import (
    advance_to_next_element_node,
    answer_question_node,
    check_interview_complete_node,
    end_conversation_node,
    error_handler_node,
    evaluate_fes_factors_node,
    export_document_node,
    finalize_node,
    gather_draft_requirements_node,
    generate_element_node,
    handle_draft_response_node,
    handle_element_revision_request,
    init_node,
    intent_classification_node,
    map_answers_node,
    prepare_next_node,
    qa_review_node,
    route_after_advance_element,
    route_after_draft_response,
    route_after_element_revision,
    route_after_end_conversation,
    route_after_error,
    route_after_export,
    route_after_finalize,
    route_after_generate_element,
    route_after_init,
    route_after_qa,
    route_by_intent,
    user_input_node,
)
from src.nodes.handle_write_another_node import handle_write_another_node
from src.nodes.reprompt_node import reprompt_node

logger = logging.getLogger(__name__)


def build_graph() -> StateGraph:
    """
    Build the PD3r conversation graph.

    Returns:
        Compiled StateGraph ready for execution
    """
    builder = StateGraph(AgentState)

    # Phase 1-2 nodes
    builder.add_node("init", init_node)
    builder.add_node("user_input", user_input_node)
    builder.add_node("classify_intent", intent_classification_node)
    builder.add_node("end_conversation", end_conversation_node)
    builder.add_node("map_answers", map_answers_node)
    builder.add_node("answer_question", answer_question_node)
    builder.add_node("prepare_next", prepare_next_node)
    builder.add_node("check_interview_complete", check_interview_complete_node)

    # Phase 3 nodes
    builder.add_node("evaluate_fes", evaluate_fes_factors_node)
    builder.add_node("gather_requirements", gather_draft_requirements_node)
    builder.add_node("generate_element", generate_element_node)
    builder.add_node("qa_review", qa_review_node)
    builder.add_node("handle_draft_response", handle_draft_response_node)
    builder.add_node("advance_element", advance_to_next_element_node)

    # Phase 4 nodes
    builder.add_node("finalize", finalize_node)
    builder.add_node("handle_element_revision", handle_element_revision_request)
    builder.add_node("handle_write_another", handle_write_another_node)
    builder.add_node("export_document", export_document_node)

    # Error recovery node - centralized error handling
    builder.add_node("error_handler", error_handler_node)

    # Reprompt node - generates clarification when intent is unrecognized
    builder.add_node("reprompt", reprompt_node)

    # Entry point
    builder.add_edge(START, "init")

    # After init, go to user_input to collect response
    builder.add_conditional_edges(
        "init",
        route_after_init,
        {
            "user_input": "user_input",
        },
    )

    # After user_input, classify the intent
    builder.add_edge("user_input", "classify_intent")

    # Route based on classified intent
    builder.add_conditional_edges(
        "classify_intent",
        route_by_intent,
        {
            "init": "init",
            "user_input": "user_input",
            "reprompt": "reprompt",  # Unrecognized intent → clarification message
            "end_conversation": "end_conversation",
            "error_handler": "error_handler",  # Error recovery
            # Phase 2 nodes
            "start_interview": "prepare_next",
            "map_answers": "map_answers",
            "answer_question": "answer_question",
            "check_interview_complete": "check_interview_complete",
            "handle_unrecognized": "prepare_next",
            # Phase 3 nodes
            "handle_draft_response": "handle_draft_response",
            # Transition from requirements phase (user confirmed interview summary)
            "evaluate_fes": "evaluate_fes",
            # Phase 4 nodes
            "finalize": "finalize",
            "handle_element_revision": "handle_element_revision",
            "handle_write_another": "handle_write_another",
            "export_document": "export_document",
        },
    )

    # After mapping answers, prepare the next question
    builder.add_edge("map_answers", "prepare_next")

    # After answering a question, go back to user_input
    builder.add_edge("answer_question", "user_input")

    # After reprompt (clarification message), wait for user input
    builder.add_edge("reprompt", "user_input")

    # After preparing next, go to user_input
    builder.add_edge("prepare_next", "user_input")

    # After checking interview complete, ALWAYS go to prepare_next
    # prepare_next handles requirements phase (shows summary and asks for confirmation)
    # User must confirm before FES evaluation begins
    builder.add_edge("check_interview_complete", "prepare_next")

    # Phase 3 edges: FES → Requirements → Generate → (QA or User) → Route
    builder.add_edge("evaluate_fes", "gather_requirements")
    builder.add_edge("gather_requirements", "generate_element")
    
    # After generating element, either go to QA or skip to user (if SKIP_QA)
    builder.add_conditional_edges(
        "generate_element",
        route_after_generate_element,
        {
            "qa_review": "qa_review",  # Normal QA flow
            "user_input": "user_input",  # SKIP_QA enabled
        },
    )

    # After QA review, route based on pass/fail/rewrite or error
    builder.add_conditional_edges(
        "qa_review",
        route_after_qa,
        {
            "generate_element": "generate_element",  # Rewrite
            "user_input": "user_input",  # Present to user
            "error_handler": "error_handler",  # Error recovery
        },
    )

    # After user approves/rejects draft
    builder.add_conditional_edges(
        "handle_draft_response",
        route_after_draft_response,
        {
            "generate_element": "generate_element",  # Rewrite requested
            "advance_element": "advance_element",  # Move to next
            "error_handler": "error_handler",  # Error recovery
        },
    )

    # After advancing, either generate next, go to review, or finish
    builder.add_conditional_edges(
        "advance_element",
        route_after_advance_element,
        {
            "generate_element": "generate_element",
            "qa_review": "qa_review",  # Already drafted, needs QA
            "user_input": "user_input",  # qa_passed elements skip generation
            "finalize": "finalize",  # All elements done - go to final review
            "end_conversation": "end_conversation",
            "error_handler": "error_handler",  # Error recovery
        },
    )

    # Phase 4 edges: Finalize flow
    builder.add_conditional_edges(
        "finalize",
        route_after_finalize,
        {
            "user_input": "user_input",  # Wait for user to choose export format
        },
    )

    # After export_document, either ask "write another?" or handle export error
    builder.add_conditional_edges(
        "export_document",
        route_after_export,
        {
            "end_conversation": "end_conversation",  # Success: ask "write another?"
            "user_input": "user_input",  # Error: user chooses different format
            "error_handler": "error_handler",  # Critical error recovery
        },
    )

    # After element revision request, either regenerate or clarify
    builder.add_conditional_edges(
        "handle_element_revision",
        route_after_element_revision,
        {
            "generate_element": "generate_element",  # Regenerate the element
            "user_input": "user_input",  # Need clarification
            "error_handler": "error_handler",  # Error recovery
        },
    )

    # After handle_write_another, go to end_conversation
    # (which will then route based on wants_another flag)
    builder.add_edge("handle_write_another", "end_conversation")

    # End conversation - route based on wants_another flag
    builder.add_conditional_edges(
        "end_conversation",
        route_after_end_conversation,
        {
            "user_input": "user_input",  # Ask "write another?"
            "init": "init",  # User wants to write another PD
            "__end__": END,  # User is done
            "error_handler": "error_handler",  # Error recovery
        },
    )

    # Error handler - always routes back to user_input for recovery
    builder.add_conditional_edges(
        "error_handler",
        route_after_error,
        {
            "user_input": "user_input",
        },
    )

    return builder


def compile_graph(checkpointer: MemorySaver | None = None):
    """
    Compile the graph with optional checkpointer.

    Args:
        checkpointer: Optional MemorySaver for state persistence

    Returns:
        Compiled graph ready for invocation
        
    Raises:
        CheckpointerError: If checkpointer setup fails
    """
    builder = build_graph()

    try:
        if checkpointer is None:
            checkpointer = MemorySaver()
        
        return builder.compile(checkpointer=checkpointer)
    except Exception as e:
        logger.error(f"Failed to compile graph with checkpointer: {e}")
        # Try without checkpointer as fallback
        try:
            logger.warning("Falling back to in-memory checkpointer")
            return builder.compile(checkpointer=MemorySaver())
        except Exception as fallback_error:
            raise CheckpointerError(
                f"Failed to compile graph: {fallback_error}",
                context={"original_error": str(e)},
            ) from fallback_error


class SafeCheckpointer:
    """
    Wrapper around checkpointer that handles errors gracefully.
    
    This wrapper catches checkpointer errors and logs them without
    crashing the graph execution. Data may be lost on failure but
    the conversation can continue.
    """
    
    def __init__(self, checkpointer: MemorySaver):
        self._checkpointer = checkpointer
        self._last_error: str | None = None
    
    @property
    def last_error(self) -> str | None:
        """Get the last error message, if any."""
        return self._last_error
    
    def put(self, *args, **kwargs) -> Any:
        """Save state with error handling."""
        try:
            self._last_error = None
            return self._checkpointer.put(*args, **kwargs)
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Checkpointer save failed: {e}")
            # Don't raise - allow conversation to continue
            return None
    
    def get(self, *args, **kwargs) -> Any:
        """Get state with error handling."""
        try:
            self._last_error = None
            return self._checkpointer.get(*args, **kwargs)
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Checkpointer load failed: {e}")
            return None
    
    def __getattr__(self, name: str) -> Any:
        """Proxy other attributes to wrapped checkpointer."""
        return getattr(self._checkpointer, name)


# Default compiled graph instance
pd_graph = compile_graph()
