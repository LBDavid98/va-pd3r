"""Finalize node for final document assembly and export.

Handles the final approval flow, document assembly, and
transitions to export functionality.
"""


import logging
import os

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from src.exceptions import ConfigurationError
from src.models.draft import DraftElement
from src.models.state import AgentState
from src.utils.document import (
    assemble_final_document,
    create_review_summary,
    get_element_by_name,
)
from src.utils.llm import traced_node, traced_structured_llm_call

logger = logging.getLogger(__name__)


# =============================================================================
# LLM ELEMENT EXTRACTION (replaces keyword heuristics per ADR-007)
# =============================================================================

class ElementExtractionResult(BaseModel):
    """LLM structured output for identifying which element user wants to modify."""
    
    element_name: str | None = Field(
        default=None,
        description="The internal element name user wants to modify, or null if unclear"
    )
    confidence: float = Field(
        ge=0, le=1,
        description="Confidence that this is the correct element (0.0-1.0)"
    )
    reasoning: str = Field(
        description="Brief explanation of why this element was identified"
    )


async def _extract_target_element(
    user_feedback: str,
    available_elements: list[str],
) -> ElementExtractionResult:
    """
    Use LLM to identify which element the user wants to modify.
    
    This replaces the previous keyword-based heuristic matching.
    Per ADR-006/ADR-007: All decision-making must be LLM-driven.
    
    Args:
        user_feedback: The user's revision request
        available_elements: List of element names that can be modified
        
    Returns:
        ElementExtractionResult with identified element or None
    """
    if not os.getenv("OPENAI_API_KEY"):
        raise ConfigurationError(
            "OPENAI_API_KEY is required for element extraction. "
            "This agent does not support heuristic fallbacks."
        )
    
    # Build element descriptions for the LLM
    element_descriptions = {
        "introduction": "Introduction - opening paragraph describing the position",
        "major_duties": "Major Duties - main job responsibilities with percentage weights",
        "factor_1_knowledge": "Factor 1: Knowledge - required knowledge, skills, and abilities",
        "factor_2_supervisory_controls": "Factor 2: Supervisory Controls - supervision received/exercised",
        "factor_3_guidelines": "Factor 3: Guidelines - rules, regulations, procedures followed",
        "factor_4_complexity": "Factor 4: Complexity - nature and variety of tasks",
        "factor_5_scope_effect": "Factor 5: Scope and Effect - impact of work",
        "factor_6_7_contacts": "Factors 6/7: Personal Contacts and Purpose of Contacts",
        "factor_8_physical_demands": "Factor 8: Physical Demands",
        "factor_9_work_environment": "Factor 9: Work Environment",
        "other_significant_factors": "Other Significant Factors - customer service, security, safety",
        "background": "Background - organizational context and history",
    }
    
    elements_text = "\n".join(
        f"- {name}: {element_descriptions.get(name, name)}"
        for name in available_elements
    )
    
    prompt = f"""Identify which section of a federal position description the user wants to modify.

User's request: "{user_feedback}"

Available sections:
{elements_text}

Instructions:
- Identify the section the user is referring to, even if they use informal terms
- "Factor 1", "knowledge section", or "KSAs" all refer to factor_1_knowledge
- "Duties", "responsibilities", "job duties" refer to major_duties
- "Intro", "opening" refer to introduction
- If the user's intent is unclear or could match multiple sections, set element_name to null

Return the internal element name (like "factor_1_knowledge") not the display name."""

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    result, _usage = await traced_structured_llm_call(
        llm=llm,
        prompt=prompt,
        output_schema=ElementExtractionResult,
        node_name="extract_target_element",
        metadata={"user_feedback": user_feedback[:100]},
    )
    
    return result


@traced_node
def finalize_node(state: AgentState) -> dict:
    """
    Handle final document assembly and review.

    This node is responsible for:
    1. Assembling all draft elements into a final document
    2. Presenting the complete PD for final review
    3. Handling late revisions to any element
    4. Preparing for export when user confirms

    Args:
        state: Current agent state

    Returns:
        State update with assembled document and next prompt
    """
    draft_elements = state.get("draft_elements", [])
    interview_data = state.get("interview_data")
    last_intent = state.get("last_intent", "")

    if not draft_elements:
        return {
            "messages": [
                AIMessage(
                    content="No draft elements available. "
                    "Let's start the interview to create your position description."
                )
            ],
            "phase": "interview",
        }

    # Check if user confirmed the final document
    if last_intent == "confirm":
        # User approved - prepare for export
        assembled_doc = assemble_final_document(draft_elements, interview_data)

        return {
            "messages": [
                AIMessage(
                    content="Your position description has been finalized.\n\n"
                    "How would you like to export it?\n"
                    "- Say **'word'** for a Word document (.docx)\n"
                    "- Say **'markdown'** for a Markdown file (.md)\n"
                    "- Or say **'done'** if you don't need to export"
                )
            ],
            "phase": "complete",
            "next_prompt": "Choose your export format, or say 'done' to finish.",
        }

    # Generate the review summary and assembled document
    review_summary = create_review_summary(draft_elements, interview_data)
    assembled_doc = assemble_final_document(draft_elements, interview_data)

    # Build the review message
    review_message = (
        "Here's your complete position description:\n\n"
        f"{review_summary}\n\n"
        "---\n\n"
        f"{assembled_doc}\n\n"
        "---\n\n"
        "**Please review the complete document above.**\n\n"
        "If everything looks good, say **'yes'** or **'approve'** to finalize.\n"
        "If you'd like to revise any section, just tell me which one "
        "(e.g., 'change the introduction' or 'revise factor 1')."
    )

    return {
        "messages": [AIMessage(content=review_message)],
        "next_prompt": "Review the document and let me know if it's ready to finalize.",
    }


@traced_node
async def handle_element_revision_request(state: AgentState) -> dict:
    """
    Handle a request to revise a specific element during review phase.

    This function uses LLM to identify which element the user wants to modify
    and prepares the state for regeneration. Per ADR-006/ADR-007, we do NOT
    use keyword heuristics for this decision.

    Args:
        state: Current agent state with element modification request

    Returns:
        State update to route to generate_element for the target element
    """
    draft_elements = state.get("draft_elements", [])
    messages = state.get("messages", [])

    # Get the last user message for feedback
    feedback = ""
    if messages:
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "human":
                feedback = msg.content
                break

    if not feedback:
        return {
            "messages": [
                AIMessage(
                    content="I'd like to help you revise a section. "
                    "Which section would you like to change?"
                )
            ],
            "next_prompt": "Please specify which section to revise.",
        }

    # Get available element names
    available_elements = [
        DraftElement.model_validate(e).name for e in draft_elements
    ]

    # Use LLM to identify the target element (NO HEURISTICS)
    extraction_result = await _extract_target_element(feedback, available_elements)
    
    element_name = extraction_result.element_name
    
    # Check confidence threshold - if LLM is unsure, ask for clarification
    if not element_name or extraction_result.confidence < 0.7:
        element_list = "\n".join(
            f"- {DraftElement.model_validate(e).display_name}"
            for e in draft_elements
        )
        clarification_msg = (
            "I want to help you revise the right section, but I'm not certain which one you mean.\n\n"
            f"Which of these sections would you like to change?\n{element_list}"
        )
        if extraction_result.reasoning:
            logger.info(f"Element extraction uncertain: {extraction_result.reasoning}")
        
        return {
            "messages": [AIMessage(content=clarification_msg)],
            "next_prompt": "Please specify which section to revise.",
        }

    # Find the element
    idx, element = get_element_by_name(draft_elements, element_name)

    if idx < 0 or element is None:
        # Element name from LLM doesn't match - shouldn't happen but handle gracefully
        logger.warning(f"LLM returned element '{element_name}' not found in draft")
        element_list = "\n".join(
            f"- {DraftElement.model_validate(e).display_name}"
            for e in draft_elements
        )
        return {
            "messages": [
                AIMessage(
                    content=f"I couldn't find a section matching '{element_name}'.\n\n"
                    f"Which section would you like to change?\n{element_list}"
                )
            ],
            "next_prompt": "Which section would you like to revise?",
        }

    # Mark element for revision with feedback
    element.request_revision(feedback)
    draft_elements[idx] = element.model_dump()

    return {
        "messages": [
            AIMessage(
                content=f"I'll revise the **{element.display_name}** based on your feedback."
            )
        ],
        "draft_elements": draft_elements,
        "current_element_index": idx,
        "current_element_name": element.name,
        "phase": "drafting",  # Temporarily back to drafting to regenerate
        "next_prompt": "",
    }


def check_all_elements_complete(draft_elements: list[dict]) -> bool:
    """
    Check if all draft elements are complete (approved or qa_passed).

    Args:
        draft_elements: List of serialized DraftElement dicts

    Returns:
        True if all elements are complete
    """
    if not draft_elements:
        return False

    for element_dict in draft_elements:
        element = DraftElement.model_validate(element_dict)
        if not element.is_complete:
            return False

    return True


def get_incomplete_elements(draft_elements: list[dict]) -> list[str]:
    """
    Get list of incomplete element names.

    Args:
        draft_elements: List of serialized DraftElement dicts

    Returns:
        List of display names for incomplete elements
    """
    incomplete = []

    for element_dict in draft_elements:
        element = DraftElement.model_validate(element_dict)
        if not element.is_complete:
            incomplete.append(element.display_name)

    return incomplete
