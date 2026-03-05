"""Human-in-the-loop tools for LLM-driven approval and review.

These tools use LangGraph's `interrupt()` function to pause execution
and collect human input before resuming. They enable:
- Requirements review after interview completion
- Section approval during drafting phase

Per ADR-006, the LLM decides when to call these tools via tool selection.
The interrupt() pauses graph execution without trapping the user - they
can still ask questions and interact while reviewing.

IMPORTANT: These tools require a checkpointer to be configured on the graph.
Without persistence, interrupt/resume will not work.

Usage:
    1. Agent calls request_requirements_review when interview is complete
    2. Graph pauses with interrupt, showing requirements summary
    3. User responds (approve, request changes, ask questions)
    4. Graph resumes with Command(resume=<user_response>)
    5. Tool returns user's response for agent to process
"""

import logging
import os
from typing import Any, Annotated, Literal

from langchain_core.tools import InjectedToolArg, tool
from langchain_openai import ChatOpenAI
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from src.config.intake_fields import INTAKE_FIELDS, BASE_INTAKE_SEQUENCE
from src.exceptions import ConfigurationError
from src.models.interview import InterviewData
from src.utils.llm import traced_structured_llm_call

logger = logging.getLogger(__name__)


def _format_interview_summary(interview_data: InterviewData) -> str:
    """Format interview data as a readable summary for human review.
    
    Args:
        interview_data: The collected interview data
        
    Returns:
        Formatted markdown summary of all collected fields
    """
    lines = [
        "# Position Description Requirements Summary",
        "",
        "Please review the following information collected during our interview:",
        "",
    ]
    
    # Group fields by category for better readability
    categories = {
        "Position Identification": ["position_title", "pay_plan", "series", "grade", "duty_location"],
        "Organization": ["agency", "organization", "direct_supervisor_title", "second_level_supervisor_title"],
        "Position Details": ["supervisory_status", "flsa_status", "competitive_level", "position_sensitivity"],
        "Duties & Responsibilities": ["major_duties", "percentage_of_time", "supervision_received"],
        "Additional Information": [],  # Catch-all for remaining fields
    }
    
    # Get all collected fields
    collected = interview_data.get_set_fields()
    fields_shown = set()
    
    for category, field_names in categories.items():
        category_fields = []
        for field_name in field_names:
            if field_name in collected:
                element = getattr(interview_data, field_name, None)
                if element and element.value is not None:
                    field_def = INTAKE_FIELDS.get(field_name)
                    display_name = field_def.prompt.split("?")[0] if field_def else field_name.replace("_", " ").title()
                    # Truncate display name if it's too long
                    if len(display_name) > 40:
                        display_name = field_name.replace("_", " ").title()
                    
                    # Format value based on type
                    value = element.value
                    if isinstance(value, dict):
                        # Format duties/percentages as list
                        value_str = "\n" + "\n".join(f"  - {k}: {v}" for k, v in value.items())
                    elif isinstance(value, list):
                        value_str = ", ".join(str(v) for v in value)
                    else:
                        value_str = str(value)
                    
                    category_fields.append(f"- **{display_name}**: {value_str}")
                    fields_shown.add(field_name)
        
        if category_fields:
            lines.append(f"## {category}")
            lines.extend(category_fields)
            lines.append("")
    
    # Add any remaining fields not in categories
    remaining = [f for f in collected if f not in fields_shown]
    if remaining:
        lines.append("## Other Information")
        for field_name in remaining:
            element = getattr(interview_data, field_name, None)
            if element and element.value is not None:
                display_name = field_name.replace("_", " ").title()
                lines.append(f"- **{display_name}**: {element.value}")
        lines.append("")
    
    # Add fields needing confirmation
    needs_confirm = interview_data.get_fields_needing_confirmation()
    if needs_confirm:
        lines.append("## ⚠️ Fields Needing Confirmation")
        for field_name in needs_confirm:
            element = getattr(interview_data, field_name, None)
            if element:
                lines.append(f"- **{field_name.replace('_', ' ').title()}**: {element.value} *(please confirm)*")
        lines.append("")
    
    # Add response instructions
    lines.extend([
        "---",
        "",
        "## Your Options",
        "",
        "Please respond with one of:",
        "- **'approve'** or **'looks good'** - Proceed to drafting the position description",
        "- **'change [field] to [value]'** - Modify a specific field",
        "- **Ask a question** - I'll answer and then return to this review",
        "",
        "You can also ask questions about any field or the process at any time.",
    ])
    
    return "\n".join(lines)


def _format_section_for_approval(
    section_name: str,
    section_content: str,
    qa_passed: bool,
    qa_confidence: float | None = None,
    qa_notes: list[str] | None = None,
) -> str:
    """Format a draft section for human approval review.
    
    Args:
        section_name: Name of the section
        section_content: The drafted content
        qa_passed: Whether QA review passed
        qa_confidence: QA confidence score (0-1)
        qa_notes: Any QA notes or concerns
        
    Returns:
        Formatted markdown for human review
    """
    display_name = section_name.replace("_", " ").title()
    
    if qa_passed:
        status_emoji = "✅"
        status_text = "Passed QA Review"
    else:
        status_emoji = "⚠️"
        status_text = "Requires Human Review"
    
    # Content is already visible in the product/draft panel — don't echo it
    # in chat. Just show status and approval options.
    lines = [
        f"**{display_name}** {status_emoji} {status_text}",
    ]

    if qa_confidence is not None:
        lines.append(f"QA Confidence: {qa_confidence:.0%}")

    if qa_notes:
        for note in qa_notes:
            lines.append(f"- {note}")

    lines.extend([
        "",
        "Review the section in the draft panel, then:",
        "- **'approve'** — Accept and proceed",
        "- **'revise: [feedback]'** — Request changes",
        "- **'reject'** — Rewrite from scratch",
    ])
    
    return "\n".join(lines)


@tool
def request_requirements_review(
    interview_data_dict: Annotated[dict, InjectedToolArg],
) -> str:
    """Request human review of collected requirements before drafting.

    Use this tool when:
    - All required interview fields have been collected
    - The check_interview_complete tool indicates completion
    - You're ready to transition from interview to drafting phase

    This tool will pause execution and show the user a summary of all
    collected information for their review. They can:
    - Approve and proceed to drafting
    - Request changes to specific fields
    - Ask questions (you'll answer and return to review)

    IMPORTANT: This uses interrupt() to pause the graph. The user's
    response will be returned as the tool result when they respond.

    Args:
        interview_data_dict: The interview data dictionary (injected from state)

    Returns:
        The user's response (approval, change request, or question)
    """
    logger.info("Tool request_requirements_review: Starting human review")
    
    # Parse interview data
    try:
        interview_data = InterviewData.model_validate(interview_data_dict)
    except Exception as e:
        logger.error(f"Failed to parse interview data: {e}")
        return f"Error preparing review: {e}. Please try again."
    
    # Format the summary for human review
    summary = _format_interview_summary(interview_data)
    
    # Interrupt and wait for human response
    # The interrupt() call pauses graph execution and sends the summary
    # to the user. When they respond with Command(resume=<response>),
    # execution resumes and their response is returned here.
    logger.info("Tool request_requirements_review: Calling interrupt()")
    
    response = interrupt(summary)
    
    logger.info(f"Tool request_requirements_review: Received response: {response[:50]}..." if len(str(response)) > 50 else f"Tool request_requirements_review: Received response: {response}")
    
    return str(response)


@tool 
def request_section_approval_with_interrupt(
    section_name: str,
    section_content: str,
    qa_passed: bool,
    qa_confidence: float | None = None,
    qa_notes: Annotated[list[str] | None, InjectedToolArg] = None,
) -> str:
    """Request human approval for a draft section using interrupt.

    Use this tool when:
    - A section has passed QA review (confidence >= 80%)
    - A section has hit the rewrite limit and needs human decision
    - The user explicitly asks to review a section

    This tool pauses execution and shows the user the section content
    for their review. They can:
    - Approve the section
    - Request revisions with feedback
    - Reject and request a complete rewrite
    - Ask questions

    IMPORTANT: This uses interrupt() to pause the graph.

    Args:
        section_name: Name of the section (e.g., 'major_duties', 'introduction')
        section_content: The drafted section content
        qa_passed: Whether the section passed QA review
        qa_confidence: QA confidence score (0-1), optional
        qa_notes: Any QA notes or concerns, optional

    Returns:
        The user's response (approval, revision request, or question)
    """
    logger.info(f"Tool request_section_approval_with_interrupt: {section_name}")
    
    if not section_content:
        return "Error: No section content provided for review."
    
    # Format the section for human review
    review_prompt = _format_section_for_approval(
        section_name=section_name,
        section_content=section_content,
        qa_passed=qa_passed,
        qa_confidence=qa_confidence,
        qa_notes=qa_notes,
    )
    
    # Interrupt and wait for human response
    logger.info(f"Tool request_section_approval_with_interrupt: Calling interrupt() for {section_name}")
    
    response = interrupt(review_prompt)
    
    logger.info(f"Tool request_section_approval_with_interrupt: Response for {section_name}: {str(response)[:50]}...")
    
    return str(response)


class ApprovalInterpretation(BaseModel):
    """LLM structured output for interpreting approval responses."""

    action: Literal["approve", "revise", "reject", "question", "change"] = Field(
        description="The user's intended action"
    )
    confidence: float = Field(
        ge=0, le=1, description="Confidence in this interpretation"
    )
    feedback: str | None = Field(
        default=None, description="Any feedback or additional context from the user"
    )
    field: str | None = Field(
        default=None, description="For 'change' action: the field to modify"
    )
    value: str | None = Field(
        default=None, description="For 'change' action: the new value"
    )
    reasoning: str = Field(description="Brief explanation of interpretation")


async def _interpret_approval_response(
    response: str,
    context: str = "section approval",
) -> ApprovalInterpretation:
    """
    Use LLM to interpret user's approval response.

    Per ADR-007: All ambiguous user input must be LLM-interpreted.
    """
    if not os.getenv("OPENAI_API_KEY"):
        raise ConfigurationError(
            "OPENAI_API_KEY required for response interpretation"
        )

    prompt = f"""Interpret the user's response to a {context} request.

User's response: "{response}"

Determine their intent:
- "approve": They want to accept/proceed (yes, ok, looks good, approve, lgtm, proceed)
- "revise": They want changes but keep the general content (revise, update, change this part)
- "reject": They want to start over completely (no, reject, rewrite, start over)
- "question": They're asking a question, not making a decision
- "change": They want to change a specific field to a specific value (change X to Y)

For "change" actions, extract the field name and new value if present.
Include any feedback or context they provided.

Be generous with approval interpretation - if they seem positive, interpret as approve.
"""

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    result, _ = await traced_structured_llm_call(
        llm=llm,
        prompt=prompt,
        output_schema=ApprovalInterpretation,
        node_name="interpret_approval",
        metadata={"response": response[:100]},
    )

    return result


def parse_approval_response(response: str) -> dict[str, Any]:
    """Parse a human's approval response into structured data.

    Uses LLM interpretation for nuanced understanding.
    Falls back to basic parsing only for extremely clear cases.

    Args:
        response: The raw user response string

    Returns:
        Dict with keys:
        - action: 'approve' | 'revise' | 'reject' | 'question' | 'change'
        - feedback: Optional feedback text
        - field: Optional field name (for change requests)
        - value: Optional new value (for change requests)
    """
    import asyncio

    response_lower = response.lower().strip()

    # Fast path for unambiguous single-word responses (optimization only)
    if response_lower in ("approve", "approved", "yes", "ok", "lgtm"):
        return {"action": "approve", "feedback": None}
    if response_lower in ("reject", "no"):
        return {"action": "reject", "feedback": None}

    # For anything else, use LLM interpretation
    try:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Already in async context
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(
                        asyncio.run, _interpret_approval_response(response)
                    ).result()
            else:
                result = loop.run_until_complete(
                    _interpret_approval_response(response)
                )
        except RuntimeError:
            result = asyncio.run(_interpret_approval_response(response))

        return {
            "action": result.action,
            "feedback": result.feedback,
            "field": result.field,
            "value": result.value,
        }
    except Exception as e:
        # Log but don't fail - return as question for clarification
        logger.warning(f"Failed to interpret approval response: {e}")
        return {"action": "question", "feedback": response}


# =============================================================================
# TOOL EXPORTS
# =============================================================================

HUMAN_TOOLS = [
    request_requirements_review,
    request_section_approval_with_interrupt,
]
