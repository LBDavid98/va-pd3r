"""QA (Quality Assurance) tools for LLM-driven draft review.

These tools wrap existing QA logic from:
- src/nodes/qa_review_node.py (QA review logic)
- src/models/draft.py (QAReview, QACheckResult models)

ARCHITECTURE NOTE: We wrap existing logic as tools for agent access,
preserving all existing business logic including thresholds.
Per ADR-006, the LLM decides which tool to call via tool selection.
"""

import asyncio
import logging
from pathlib import Path
from typing import Literal

from jinja2 import Environment, FileSystemLoader
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from src.models.draft import DraftElement, QACheckResult, QAReview
from src.models.requirements import DraftRequirement, DraftRequirements
from src.utils.llm import traced_structured_llm_call

logger = logging.getLogger(__name__)

# Setup Jinja environment for templates
TEMPLATES_DIR = Path(__file__).parent.parent / "prompts" / "templates"
jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))

# QA thresholds (from qa_review_node.py)
QA_PASS_THRESHOLD = 0.8
QA_REWRITE_THRESHOLD = 0.5
MAX_REWRITES = 1  # Maximum rewrite attempts per section


# =============================================================================
# SCHEMAS FOR STRUCTURED OUTPUT
# =============================================================================

class QACheckResultSchema(BaseModel):
    """Schema for LLM structured output - single check result."""
    requirement_id: str
    passed: bool
    confidence: float = Field(ge=0, le=1)
    explanation: str
    severity: Literal["critical", "warning", "info"] = "critical"
    suggestion: str | None = None


class QAReviewSchema(BaseModel):
    """Schema for LLM structured output - complete review."""
    overall_passes: bool
    overall_confidence: float = Field(ge=0, le=1)
    overall_feedback: str
    check_results: list[QACheckResultSchema]
    needs_rewrite: bool
    suggested_revisions: list[str] = Field(default_factory=list)


# =============================================================================
# HELPER FUNCTIONS (from qa_review_node.py)
# =============================================================================

def _build_qa_context(
    section_name: str,
    section_display_name: str,
    draft_content: str,
    requirements: DraftRequirements,
) -> dict:
    """Build context for QA review template."""
    element_reqs = requirements.get_requirements_for_element(section_name)
    
    return {
        "section_name": section_name,
        "section_display_name": section_display_name,
        "draft_content": draft_content,
        "requirements": [
            {
                "id": req.id,
                "description": req.description,
                "check_type": req.check_type,
                # Use 'keywords' key for template compatibility, but get from target_content
                "keywords": req.target_content,
                "is_exclusion": req.is_exclusion,
                "is_critical": req.is_critical,
                "source": req.source,
                "min_weight": req.min_weight,
                "max_weight": req.max_weight,
            }
            for req in element_reqs
        ],
    }


def _convert_schema_to_model(schema: QAReviewSchema) -> QAReview:
    """Convert LLM schema to internal QAReview model."""
    check_results = [
        QACheckResult(
            requirement_id=r.requirement_id,
            passed=r.passed,
            explanation=r.explanation,
            severity=r.severity,
            suggestion=r.suggestion,
        )
        for r in schema.check_results
    ]
    
    return QAReview(
        passes=schema.overall_passes,
        check_results=check_results,
        overall_feedback=schema.overall_feedback,
        needs_rewrite=schema.needs_rewrite,
        suggested_revisions=schema.suggested_revisions,
    )


async def _run_qa_review(
    section_name: str,
    section_display_name: str,
    draft_content: str,
    requirements: DraftRequirements,
) -> tuple[QAReview, float]:
    """Run QA review using LLM.
    
    Returns:
        Tuple of (QAReview, overall_confidence)
    """
    element_reqs = requirements.get_requirements_for_element(section_name)
    
    # No requirements = auto-pass
    if not element_reqs:
        return QAReview(
            passes=True,
            check_results=[],
            overall_feedback="No specific requirements to check",
            needs_rewrite=False,
            suggested_revisions=[],
        ), 1.0
    
    context = _build_qa_context(section_name, section_display_name, draft_content, requirements)
    template = jinja_env.get_template("qa_review.jinja")
    prompt = template.render(**context)
    
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    
    try:
        result, _usage = await traced_structured_llm_call(
            llm=llm,
            prompt=prompt,
            output_schema=QAReviewSchema,
            node_name=f"qa_tool:{section_name}",
            metadata={"section": section_name},
        )
        qa_review = _convert_schema_to_model(result)
        return qa_review, result.overall_confidence
    except Exception as e:
        logger.error(f"QA review error: {e}")
        return QAReview(
            passes=False,
            check_results=[],
            overall_feedback=f"QA review error: {str(e)}",
            needs_rewrite=False,
            suggested_revisions=[],
        ), 0.0


# =============================================================================
# QA TOOLS
# =============================================================================

@tool
def qa_review_section(
    section_name: str,
    draft_content: str,
    requirements_dict: dict,
    section_display_name: str | None = None,
) -> str:
    """Review a drafted section against requirements.

    Use this tool after writing or revising a section to check if it meets
    the requirements. Returns confidence scores and specific feedback.

    Args:
        section_name: Name of the section being reviewed
        draft_content: The draft content to review
        requirements_dict: Draft requirements as dict
        section_display_name: Human-readable section name (optional)

    Returns:
        Formatted QA review results including pass/fail status, 
        confidence score, and specific feedback
    """
    logger.info(f"Tool qa_review_section: {section_name}")
    
    if not draft_content:
        return "Error: No draft content provided for review"
    
    # Parse requirements
    try:
        requirements = DraftRequirements.model_validate(requirements_dict)
    except Exception as e:
        return f"Error parsing requirements: {e}"
    
    display_name = section_display_name or section_name.replace("_", " ").title()
    
    # Run QA review
    try:
        qa_review, confidence = asyncio.get_event_loop().run_until_complete(
            _run_qa_review(section_name, display_name, draft_content, requirements)
        )
    except RuntimeError:
        qa_review, confidence = asyncio.run(
            _run_qa_review(section_name, display_name, draft_content, requirements)
        )
    
    # Format response
    status_emoji = "✅" if qa_review.passes else "❌"
    lines = [
        f"## QA Review: {display_name}",
        f"**Status**: {status_emoji} {'PASSED' if qa_review.passes else 'FAILED'}",
        f"**Confidence**: {confidence:.0%}",
        f"**Pass Threshold**: {QA_PASS_THRESHOLD:.0%}",
        "",
        f"**Feedback**: {qa_review.overall_feedback}",
        "",
    ]
    
    # Check results
    passed_count = qa_review.passed_count
    total_count = len(qa_review.check_results)
    if total_count > 0:
        lines.append(f"**Requirements**: {passed_count}/{total_count} passed")
        lines.append("")
    
    # Failed checks
    failed = [c for c in qa_review.check_results if not c.passed]
    if failed:
        lines.append("**Failed Checks**:")
        for check in failed:
            lines.append(f"- [{check.severity}] {check.requirement_id}: {check.explanation}")
            if check.suggestion:
                lines.append(f"  → Suggestion: {check.suggestion}")
        lines.append("")
    
    # Suggested revisions
    if qa_review.suggested_revisions:
        lines.append("**Suggested Revisions**:")
        for rev in qa_review.suggested_revisions:
            lines.append(f"- {rev}")
        lines.append("")
    
    # Guidance on next steps
    if qa_review.passes:
        lines.append("✅ This section passes QA. You can proceed to request approval.")
    elif qa_review.needs_rewrite:
        lines.append(f"⚠️ This section needs revision. Use `revise_section` with the feedback above.")
    else:
        lines.append("ℹ️ Minor issues found. Consider revising or proceed to approval.")
    
    return "\n".join(lines)


@tool
def check_qa_status(draft_elements_list: list[dict]) -> str:
    """Check QA status across all draft elements.

    Use this tool to get an overview of QA progress and identify
    sections that need attention.

    Args:
        draft_elements_list: List of DraftElement dicts from state

    Returns:
        Formatted QA status summary
    """
    logger.info("Tool check_qa_status")
    
    if not draft_elements_list:
        return "No draft elements to review."
    
    lines = ["## QA Status Overview", ""]
    
    qa_passed = []
    qa_failed = []
    needs_review = []
    approved = []
    
    for elem_dict in draft_elements_list:
        try:
            elem = DraftElement.model_validate(elem_dict)
            name = elem.display_name or elem.name
            
            if elem.status == "approved":
                approved.append(name)
            elif elem.status == "qa_passed":
                qa_passed.append(name)
            elif elem.status == "needs_revision":
                rewrite_info = f" (attempt {elem.revision_count + 1}/{MAX_REWRITES + 1})"
                qa_failed.append(f"{name}{rewrite_info}")
            elif elem.content:  # Has content but not reviewed
                needs_review.append(name)
        except Exception:
            continue
    
    if approved:
        lines.append(f"✅ **Approved**: {', '.join(approved)}")
    if qa_passed:
        lines.append(f"🔍 **Passed QA**: {', '.join(qa_passed)}")
    if qa_failed:
        lines.append(f"❌ **Failed QA**: {', '.join(qa_failed)}")
    if needs_review:
        lines.append(f"⏳ **Needs QA Review**: {', '.join(needs_review)}")
    
    # Summary
    total = len(draft_elements_list)
    done = len(approved) + len(qa_passed)
    lines.extend([
        "",
        f"**QA Progress**: {done}/{total} sections passed QA",
        f"**Pass Threshold**: {QA_PASS_THRESHOLD:.0%} confidence",
        f"**Max Rewrites**: {MAX_REWRITES} per section",
    ])
    
    return "\n".join(lines)


@tool
def request_qa_rewrite(
    section_name: str,
    qa_feedback: str,
    qa_failures: list[str],
    revision_count: int = 0,
) -> str:
    """Request a rewrite for a section that failed QA.

    Use this tool when a section needs revision based on QA feedback.
    Checks rewrite limits before allowing revision.

    Args:
        section_name: Name of the section needing rewrite
        qa_feedback: Overall feedback from QA
        qa_failures: List of failed requirement IDs
        revision_count: Current revision count for the section

    Returns:
        Instructions for rewrite or message if limit reached
    """
    logger.info(f"Tool request_qa_rewrite: {section_name} (revision #{revision_count + 1})")
    
    # Check rewrite limit
    if revision_count >= MAX_REWRITES:
        return (
            f"⚠️ **Rewrite Limit Reached** for {section_name}\n\n"
            f"This section has been revised {revision_count} time(s), which is the maximum allowed.\n\n"
            "**Options**:\n"
            "1. Request human approval as-is with QA notes\n"
            "2. Request manual human revision\n\n"
            "Use `request_section_approval` to proceed."
        )
    
    lines = [
        f"## Rewrite Authorized: {section_name}",
        f"**Revision Attempt**: {revision_count + 1}/{MAX_REWRITES + 1}",
        "",
        "**QA Feedback**:",
        qa_feedback,
        "",
    ]
    
    if qa_failures:
        lines.append("**Failed Requirements**:")
        for failure in qa_failures:
            lines.append(f"- {failure}")
        lines.append("")
    
    lines.extend([
        "**Instructions**:",
        f"Use `revise_section` for '{section_name}' with the above feedback.",
        "Then run `qa_review_section` on the revised content.",
    ])
    
    return "\n".join(lines)


@tool
def request_section_approval(
    section_name: str,
    section_content: str,
    qa_passed: bool,
    qa_confidence: float | None = None,
    qa_notes: list[str] | None = None,
) -> str:
    """Request human approval for a section.

    Use this tool when:
    - Section has passed QA and is ready for approval
    - Section has hit rewrite limit and needs human review
    - User explicitly asks to review the section

    Args:
        section_name: Name of the section
        section_content: The section content for review
        qa_passed: Whether the section passed QA
        qa_confidence: QA confidence score (0-1)
        qa_notes: Any QA notes or concerns

    Returns:
        Formatted approval request for human
    """
    logger.info(f"Tool request_section_approval: {section_name} (qa_passed={qa_passed})")
    
    if qa_passed:
        status = "✅ Passed QA"
    else:
        status = "⚠️ Requires human review"
    
    lines = [
        f"## Section Ready for Approval: {section_name}",
        f"**QA Status**: {status}",
    ]
    
    if qa_confidence is not None:
        lines.append(f"**QA Confidence**: {qa_confidence:.0%}")
    
    if qa_notes:
        lines.append("")
        lines.append("**QA Notes**:")
        for note in qa_notes:
            lines.append(f"- {note}")
    
    lines.extend([
        "",
        "---",
        "**Section Content**:",
        "",
        section_content,
        "",
        "---",
        "",
        "**Please respond with**:",
        "- 'approve' to approve this section",
        "- 'reject' with feedback to request changes",
        "- 'skip' to move to next section without approval",
    ])
    
    return "\n".join(lines)


@tool
def get_qa_thresholds() -> str:
    """Get the current QA threshold settings.

    Use this tool to understand the QA pass/fail criteria.

    Returns:
        QA threshold configuration
    """
    return (
        "## QA Thresholds\n\n"
        f"**Pass Threshold**: {QA_PASS_THRESHOLD:.0%} confidence\n"
        f"**Rewrite Threshold**: {QA_REWRITE_THRESHOLD:.0%} confidence\n"
        f"**Max Rewrites**: {MAX_REWRITES} per section\n\n"
        "**How it works**:\n"
        f"- Confidence >= {QA_PASS_THRESHOLD:.0%}: Section passes QA\n"
        f"- Confidence < {QA_PASS_THRESHOLD:.0%} but >= {QA_REWRITE_THRESHOLD:.0%}: Rewrite recommended\n"
        f"- Confidence < {QA_REWRITE_THRESHOLD:.0%}: Major revision needed\n"
        f"- After {MAX_REWRITES} rewrite(s): Human review required"
    )


# =============================================================================
# TOOL EXPORTS
# =============================================================================

QA_TOOLS = [
    qa_review_section,
    check_qa_status,
    request_qa_rewrite,
    request_section_approval,
    get_qa_thresholds,
]
