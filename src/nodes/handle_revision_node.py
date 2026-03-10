"""Handle revision node for user feedback on draft elements.

Processes user approval or rejection of draft elements and
manages the flow to the next element or revision.
"""

from langchain_core.messages import AIMessage

from src.models.draft import DraftElement, find_actionable_indices, find_next_ready_index, find_ready_indices
from src.models.state import AgentState
from src.utils.llm import traced_node
from src.utils.state_compactor import compact_after_element_approved


@traced_node
def handle_draft_response_node(state: AgentState) -> dict:
    """
    Handle user response to a draft element (approve/reject).

    Based on intent classification:
    - confirm: Approve current element, move to next
    - reject: Mark for revision with feedback
    - provide_information: Treat as revision feedback

    Args:
        state: Current agent state

    Returns:
        State update with next action
    """
    # Get current element
    element_index = state.get("current_element_index", 0)
    draft_elements = state.get("draft_elements", [])
    
    if not draft_elements or element_index >= len(draft_elements):
        return {
            "messages": [AIMessage(content="No element to process.")],
            "phase": "review",
        }
    
    element_dict = draft_elements[element_index]
    element = DraftElement.model_validate(element_dict)
    
    # Get the user's intent from classification
    last_intent = state.get("last_intent", "")
    
    if last_intent == "confirm":
        # User approved the element
        element.approve()
        draft_elements[element_index] = element.model_dump()

        # Compact the approved element's verbose history
        compaction = compact_after_element_approved(
            {"draft_elements": draft_elements}, element_index
        )
        if compaction.get("draft_elements"):
            draft_elements = compaction["draft_elements"]

        # Import here to avoid circular dependency
        from src.utils.personality import get_confirmation_success
        success_phrase = get_confirmation_success()

        # Check for next actionable element (includes qa_passed, not just pending/drafted)
        ready_indices = find_actionable_indices(draft_elements)
        if ready_indices:
            ready_index = ready_indices[0]
            next_element = DraftElement.model_validate(draft_elements[ready_index])
            already_reviewed = next_element.status == "qa_passed"
            action_msg = (
                f"Review: {next_element.display_name}"
                if already_reviewed
                else ""
            )
            return {
                "messages": [
                    AIMessage(
                        content=f"{success_phrase} **{element.display_name}** approved!\n\n"
                        f"Moving to next section: {next_element.display_name}"
                    )
                ],
                "draft_elements": draft_elements,
                "current_element_index": ready_index,
                "current_element_name": next_element.name,
                "next_prompt": action_msg,
            }
        # All elements complete
        return {
            "messages": [
                AIMessage(
                    content=f"{success_phrase} **{element.display_name}** approved!\n\n"
                    "🎉 All sections have been drafted and approved! "
                    "Ready to assemble the final position description."
                )
            ],
            "draft_elements": draft_elements,
            "phase": "review",
            "next_prompt": "Would you like me to assemble the final document?",
        }
    
    elif last_intent == "reject":
        # User rejected - get their feedback from the message
        messages = state.get("messages", [])
        user_feedback = ""
        if messages:
            last_msg = messages[-1]
            if hasattr(last_msg, "content"):
                user_feedback = last_msg.content
        
        # Save current draft to history before revision (4.3.D)
        element.save_to_history(reason="user_revision")
        
        element.request_revision(user_feedback)
        draft_elements[element_index] = element.model_dump()
        
        if element.can_rewrite:
            # Import here to avoid circular dependency
            from src.utils.personality import get_revision_acknowledgment
            return {
                "messages": [
                    AIMessage(
                        content=f"{get_revision_acknowledgment()} I'll revise **{element.display_name}** based on your feedback."
                    )
                ],
                "draft_elements": draft_elements,
                "next_prompt": "",
            }
        else:
            return {
                "messages": [
                    AIMessage(
                        content=f"We've already revised {element.display_name} once. "
                        "I'll note your feedback, but let's continue with the current version "
                        "and you can make manual edits to the final document."
                    )
                ],
                "draft_elements": draft_elements,
                "next_prompt": "Shall we continue to the next section?",
            }
    
    else:
        # Other intent - treat as feedback/modification request
        messages = state.get("messages", [])
        user_feedback = ""
        if messages:
            last_msg = messages[-1]
            if hasattr(last_msg, "content"):
                user_feedback = last_msg.content
        
        return {
            "messages": [
                AIMessage(
                    content=f"I heard your feedback on {element.display_name}. "
                    "Would you like me to revise it, or shall we approve and continue?"
                )
            ],
            "next_prompt": "Please say 'yes' to approve or 'no' to revise.",
        }


@traced_node
def advance_to_next_element_node(state: AgentState) -> dict:
    """
    Advance to the next draft element.

    Used after an element is approved to move to the next one.

    Args:
        state: Current agent state

    Returns:
        State update pointing to next element
    """
    element_index = state.get("current_element_index", 0)
    draft_elements = state.get("draft_elements", [])
    
    ready_index = find_next_ready_index(draft_elements)

    if ready_index is None:
        # All elements complete or waiting on prerequisites
        return {
            "messages": [
                AIMessage(
                    content="All sections have been drafted! "
                    "Ready to assemble the final position description."
                )
            ],
            "phase": "review",
            "next_prompt": "Would you like me to assemble the final document?",
        }

    next_element = DraftElement.model_validate(draft_elements[ready_index])

    return {
        "current_element_index": ready_index,
        "current_element_name": next_element.name,
        "messages": [
            AIMessage(
                content=f"Moving to: {next_element.display_name}"
            )
        ],
        "next_prompt": "",
    }
