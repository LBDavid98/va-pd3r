"""Routing logic for conditional edges in the graph."""

import logging
from typing import Literal

from src.constants import SKIP_QA, STOP_AT
from src.models.state import AgentState

logger = logging.getLogger(__name__)


# Type alias for routing destinations
RouteDestination = Literal[
    "init",
    "user_input",
    "classify_intent",
    "start_interview",
    "map_answers",
    "answer_question",
    "check_interview_complete",
    "end_conversation",
    "handle_unrecognized",
    "error_handler",  # Centralized error recovery
    # Phase 3 destinations
    "handle_draft_response",
    "generate_element",
    "advance_element",
    "evaluate_fes",  # Transition from requirements phase to drafting
    "qa_review",  # QA review after element generation
    # Phase 4 destinations
    "finalize",  # Final document assembly and review
    "handle_element_revision",  # Revise element during review phase
    "handle_write_another",  # Handle "write another?" response
    "export_document",  # Export to markdown or Word
]


def _check_for_error(state: AgentState) -> bool:
    """Check if state has an error that needs handling.
    
    Args:
        state: Current agent state
        
    Returns:
        True if last_error is set and non-empty
    """
    return bool(state.get("last_error"))


def route_by_intent(state: AgentState) -> RouteDestination:
    """
    Route to appropriate handler based on classified intent.

    This is the main routing function used for conditional edges
    after intent classification.

    Args:
        state: Current agent state with last_intent

    Returns:
        Name of the next node to execute
    """
    # Check for errors first - route to error handler for recovery
    if _check_for_error(state):
        logger.info("Error detected in state, routing to error_handler")
        return "error_handler"
    
    intent = state.get("last_intent", "unrecognized")
    phase = state.get("phase", "init")

    # System commands - always take precedence
    if intent == "quit":
        return "end_conversation"

    if intent == "request_restart":
        return "init"

    # Phase-specific routing
    if phase == "init":
        return _route_init_phase(intent, state)

    if phase == "interview":
        return _route_interview_phase(intent, state)

    if phase == "requirements":
        return _route_requirements_phase(intent)

    if phase == "drafting":
        return _route_drafting_phase(intent, state)

    if phase == "review":
        return _route_review_phase(intent)

    if phase == "complete":
        return _route_complete_phase(intent, state)

    # Default fallback
    return "handle_unrecognized"


def _route_init_phase(intent: str, state: AgentState) -> RouteDestination:
    """Route decisions during init phase.
    
    In init phase, the user should either:
    - Confirm they want to write a PD (→ start interview)
    - Ask a question first (→ answer question)
    - Reject (→ end conversation)
    - Provide info along with confirmation (→ map answers then interview)
    
    Ambiguous inputs like "Hi there" should NOT start the interview.
    """
    # If user provided information (e.g., "yes, a Staff Assistant GS-12"),
    # route to map_answers to save the data before starting interview
    if intent == "provide_information":
        field_mappings = state.get("_field_mappings", [])
        if field_mappings:
            return "map_answers"
        # No actual field data extracted - treat as needing clarification
        # Don't start interview on ambiguous "provide_information"
        return "user_input"
    
    if intent == "confirm":
        return "start_interview"

    if intent == "reject":
        return "end_conversation"

    if intent == "ask_question":
        return "answer_question"

    # For unrecognized or other intents, re-prompt 
    return "user_input"


def _route_interview_phase(intent: str, state: AgentState) -> RouteDestination:
    """Route decisions during interview phase.
    
    DEPRECATED: This heuristic routing function is replaced by LLM-driven
    tool selection in src/agents/interview_agent.py. The LLM now decides
    which tool to call (save_field_answer, answer_user_question, etc.)
    instead of this if/else routing.
    
    Remove this function once interview_agent is integrated into main_graph.
    See: docs/decisions/006-llm-driven-routing.md
    See: docs/plans/langgraph_migration_plan.md (Phase 1, Task 1.6)
    """
    import warnings
    warnings.warn(
        "_route_interview_phase() is deprecated. Use interview_agent with LLM-driven "
        "tool selection instead. See docs/decisions/006-llm-driven-routing.md",
        DeprecationWarning,
        stacklevel=2
    )
    
    # Check if there are fields needing confirmation first
    fields_needing_confirmation = state.get("fields_needing_confirmation", [])

    if intent == "ask_question":
        return "answer_question"

    if intent == "provide_information":
        return "map_answers"

    if intent == "confirm":
        if fields_needing_confirmation:
            # Confirming a specific field
            return "map_answers"
        # Confirming interview is complete
        return "check_interview_complete"

    if intent == "reject":
        # User rejecting suggested value
        return "map_answers"

    if intent == "modify_answer":
        return "map_answers"

    return "user_input"


def _route_requirements_phase(intent: str) -> RouteDestination:
    """
    Route decisions during requirements phase.

    This is the transitional phase between interview completion and drafting.
    The user has seen the interview summary and is being asked to confirm.

    Key routing:
    - confirm: User approves the summary → start FES evaluation (unless STOP_AT)
    - modify_answer: User wants to change something → map_answers (back to interview)
    - reject: User disagrees with something → map_answers (back to interview)
    - ask_question: Still allowed mid-flow
    """
    if intent == "confirm":
        # Check if we should stop at interview phase (STOP_AT="interview")
        # Interview just completed, user confirmed the summary
        if STOP_AT == "interview":
            logger.info("STOP_AT=interview: Ending after interview confirmation")
            return "end_conversation"
        
        # Check if we should stop at requirements phase
        if STOP_AT == "requirements":
            logger.info("STOP_AT=requirements: Ending after requirements confirmation")
            return "end_conversation"
        
        # User confirmed the interview summary - proceed to FES evaluation
        return "evaluate_fes"

    if intent == "ask_question":
        return "answer_question"

    if intent in ("modify_answer", "reject"):
        # User wants to change something - go back to interview flow
        return "map_answers"

    if intent == "provide_information":
        # User providing additional info - treat as modification
        return "map_answers"

    # Default - wait for clear confirmation
    return "user_input"


def _route_drafting_phase(intent: str, state: AgentState) -> RouteDestination:
    """Route decisions during drafting phase."""
    # User responding to draft element
    if intent in ("confirm", "reject"):
        return "handle_draft_response"

    if intent == "ask_question":
        return "answer_question"

    if intent == "modify_answer":
        return "handle_element_revision"

    # Unsolicited info treated as revision request on a specific element
    if intent == "provide_information":
        return "handle_element_revision"

    # Default - stay on user input for clarification
    return "user_input"


def _route_review_phase(intent: str) -> RouteDestination:
    """
    Route decisions during review phase.

    The review phase is when the complete PD is presented for final approval.
    User can:
    - confirm: Finalize and proceed to export
    - modify_answer: Request changes to a specific element
    - ask_question: Ask clarifying questions
    - provide_information: Treat as element feedback

    Args:
        intent: The classified intent

    Returns:
        Route destination
    """
    if intent == "confirm":
        return "finalize"  # Finalize and prepare for export

    if intent == "modify_answer":
        return "handle_element_revision"  # Route to element revision handler

    if intent == "ask_question":
        return "answer_question"

    # Unsolicited info treated as feedback - route to element revision
    if intent == "provide_information":
        return "handle_element_revision"

    return "user_input"


def _route_complete_phase(intent: str, state: AgentState) -> RouteDestination:
    """
    Route decisions during complete phase (after finalization).

    The complete phase handles export and "write another?" flow:
    - request_export (with format): User chooses export format → export_document
    - request_export (format=none): User declines export → handle_write_another
    - confirm: User wants to write another PD → handle_write_another
    - reject: User is done → handle_write_another

    Args:
        intent: The classified intent
        state: Current agent state (for checking export format)

    Returns:
        Route destination
    """
    # Export request - check if user is actually requesting export or declining
    if intent == "request_export":
        # Check if export format is "none" - meaning user is declining, not requesting
        intent_data = state.get("intent_classification")
        if intent_data:
            export_request = getattr(intent_data, "export_request", None)
            if export_request and getattr(export_request, "format", None) == "none":
                # User said "no" or "done" to export - treat as decline
                return "handle_write_another"
        
        # Also check raw message for common decline patterns
        messages = state.get("messages", [])
        if messages:
            last_msg = messages[-1]
            if hasattr(last_msg, "content"):
                content = last_msg.content.lower().strip()
                # Direct declines should go to handle_write_another
                if content in ("no", "nope", "done", "no thanks", "i'm done", "im done"):
                    return "handle_write_another"
        
        # Actual export request
        return "export_document"

    # Confirm/reject for "write another?" question
    if intent in ("confirm", "reject"):
        return "handle_write_another"

    if intent == "ask_question":
        return "answer_question"

    # Default - stay on user input for clarification
    return "user_input"


def route_after_init(state: AgentState) -> RouteDestination:
    """
    Route after init node.

    Always goes to user_input to collect initial response.
    """
    return "user_input"


def route_after_draft_response(state: AgentState) -> RouteDestination:
    """
    Route after user responds to a draft element.

    Checks if the current draft element needs revision (user rejected)
    or if we should advance to the next element (user approved).

    Args:
        state: Current agent state with draft_elements and current_element_index

    Returns:
        - "error_handler" if an error occurred
        - "generate_element" if element needs revision
        - "advance_element" if element was approved
    """
    # Check for errors first
    if _check_for_error(state):
        logger.info("Error detected after draft response, routing to error_handler")
        return "error_handler"
    
    draft_elements = state.get("draft_elements", [])
    element_index = state.get("current_element_index", 0)

    # Safely access the current element
    if draft_elements and element_index < len(draft_elements):
        element = draft_elements[element_index]
        if element.get("status") == "needs_revision":
            return "generate_element"

    return "advance_element"


def route_after_advance_element(state: AgentState) -> RouteDestination:
    """
    Route after advancing to next draft element.

    Checks if we're still in drafting phase (more elements to generate)
    or if drafting is complete (move to review phase for final approval).

    Args:
        state: Current agent state with phase

    Returns:
        - "error_handler" if an error occurred
        - "user_input" if next element is already qa_passed (present for approval)
        - "generate_element" if still drafting and element needs generation
        - "finalize" if drafting complete (all elements done), unless STOP_AT=drafting
        - "end_conversation" if already in complete phase or STOP_AT triggered
    """
    # Check for errors first
    if _check_for_error(state):
        logger.info("Error detected after advance element, routing to error_handler")
        return "error_handler"

    phase = state.get("phase", "")

    if phase == "drafting":
        # If the current element is already qa_passed, present directly to user
        # instead of cycling through generate→QA needlessly.
        element_index = state.get("current_element_index", 0)
        draft_elements = state.get("draft_elements", [])
        if draft_elements and element_index < len(draft_elements):
            status = draft_elements[element_index].get("status")
            if status == "qa_passed":
                return "user_input"
        return "generate_element"

    if phase == "review":
        # Check if we should stop after drafting phase
        if STOP_AT == "drafting":
            logger.info("STOP_AT=drafting: Ending after drafting phase")
            return "end_conversation"
        return "finalize"

    return "end_conversation"


def route_should_end(state: AgentState) -> Literal["end_conversation", "user_input"]:
    """
    Check if conversation should end.

    Used as a simple conditional edge to terminate the graph.
    """
    if state.get("should_end", False):
        return "end_conversation"
    return "user_input"


def route_after_qa(state: AgentState) -> RouteDestination:
    """
    Route after QA review based on element state.

    Consolidates all rewrite limit logic in one place:
    - If error occurred: route to error handler
    - If QA passed: present to user for approval
    - If QA failed and can rewrite (revision_count < 1): rewrite
    - If QA failed and hit rewrite limit: present to user anyway

    Args:
        state: Current agent state with draft_elements

    Returns:
        - "error_handler" if an error occurred during QA
        - "generate_element" if element needs rewrite and can be rewritten
        - "user_input" if element should be presented to user for approval
    """
    # Check for errors first
    if _check_for_error(state):
        logger.info("Error detected after QA, routing to error_handler")
        return "error_handler"
    
    from src.models.draft import DraftElement

    draft_elements = state.get("draft_elements", [])
    element_index = state.get("current_element_index", 0)

    # Safely access the current element
    if not draft_elements or element_index >= len(draft_elements):
        return "user_input"

    element_dict = draft_elements[element_index]
    element = DraftElement.model_validate(element_dict)

    # Check if QA passed
    if element.qa_passed:
        return "user_input"  # Present to user for approval

    # QA failed - check if we can rewrite
    if element.can_rewrite:
        return "generate_element"  # Rewrite

    # Hit rewrite limit - present to user anyway
    return "user_input"


def route_after_finalize(state: AgentState) -> RouteDestination:
    """
    Route after finalize node.

    Based on the phase:
    - If complete: Wait for user input (to select export format)
    - Otherwise: Wait for user input

    Args:
        state: Current agent state

    Returns:
        Route destination
    """
    # Always go to user_input to let user choose export format
    return "user_input"


def route_after_export(state: AgentState) -> Literal["error_handler", "end_conversation", "user_input"]:
    """
    Route after export_document node.

    On successful export (or user declining export), routes to end_conversation
    which will ask "write another?" 
    
    On export error (user needs to choose different format), stays on user_input.
    On critical error (e.g., file system), routes to error_handler.

    Args:
        state: Current agent state

    Returns:
        Route destination
    """
    # Check for critical errors first - route to error handler
    last_error = state.get("last_error", "")
    if last_error:
        # Critical errors (not just format issues) go to error_handler
        if any(err in last_error for err in ["Permission", "IOError", "OSError", "FileSystem"]):
            logger.info("Critical export error detected, routing to error_handler")
            return "error_handler"
        # Format-related errors let user choose different format
        return "user_input"
    
    # Check if there's a prompt asking user to choose format (error case)
    next_prompt = state.get("next_prompt", "")
    if "format" in next_prompt.lower():
        return "user_input"
    
    # Success case - go to end_conversation to ask "write another?"
    return "end_conversation"


def route_after_element_revision(state: AgentState) -> RouteDestination:
    """
    Route after handling element revision request.

    If we identified an element to revise, go to generate_element.
    Otherwise stay on user_input for clarification.

    Args:
        state: Current agent state

    Returns:
        - "error_handler" if an error occurred
        - "generate_element" if element identified for revision
        - "user_input" if clarification needed
    """
    # Check for errors first
    if _check_for_error(state):
        logger.info("Error detected after element revision, routing to error_handler")
        return "error_handler"
    
    # Check if we have a valid element to regenerate
    current_element_name = state.get("current_element_name")
    phase = state.get("phase", "")

    if current_element_name and phase == "drafting":
        return "generate_element"

    return "user_input"


def route_after_end_conversation(
    state: AgentState,
) -> Literal["error_handler", "init", "user_input", "__end__"]:
    """
    Route after end_conversation node.

    Determines flow based on wants_another state:
    - Error: Go to error_handler for recovery
    - None: Go to user_input to ask "write another?"
    - True: Go to init to start a new PD
    - False: Go to __end__ to terminate

    Args:
        state: Current agent state with wants_another flag

    Returns:
        - "error_handler" if an error occurred
        - "user_input" if we need to ask "write another?"
        - "init" if user wants to write another PD
        - "__end__" if conversation should truly end
    """
    # Check for errors first
    if _check_for_error(state):
        logger.info("Error detected after end conversation, routing to error_handler")
        return "error_handler"
    
    wants_another = state.get("wants_another")

    # If not asked yet, go to user_input to get response
    if wants_another is None:
        return "user_input"

    # If user wants another, restart
    if wants_another is True:
        return "init"

    # User is done
    return "__end__"


def route_after_generate_element(state: AgentState) -> RouteDestination:
    """
    Route after generating a draft element.

    If SKIP_QA is enabled, skip QA review and go directly to user presentation.
    Otherwise, route to QA review as normal.

    Args:
        state: Current agent state

    Returns:
        - "user_input" if SKIP_QA is enabled
        - "qa_review" for normal QA flow
    """
    if SKIP_QA:
        logger.info("SKIP_QA=true: Skipping QA review, presenting draft to user")
        return "user_input"
    
    return "qa_review"
