"""QA Review node for draft elements.

Scores confidence that each requirement is present in the draft.
Routes to either:
- User approval (if passes or hit rewrite limit)
- Rewrite (if fails and can still rewrite)

All QA reports are saved to element.qa_history.
"""

import asyncio
import logging
from pathlib import Path
from typing import Literal

from jinja2 import Environment, FileSystemLoader
from langchain_core.messages import AIMessage

from pydantic import BaseModel, Field

from src.config.drafting_sections import get_generation_tier
from src.models.draft import DraftElement, QACheckResult, QAReview, find_ready_indices
from src.models.requirements import DraftRequirements
from src.models.state import AgentState
from src.utils.llm import get_chat_model, traced_node, traced_structured_llm_call

logger = logging.getLogger(__name__)

# Setup Jinja environment
TEMPLATES_DIR = Path(__file__).parent.parent / "prompts" / "templates"
jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))

# Confidence threshold for passing QA
QA_PASS_THRESHOLD = 0.8
QA_REWRITE_THRESHOLD = 0.5

# Concurrency control for parallel QA
QA_CONCURRENCY_LIMIT = 4
_qa_semaphore: asyncio.Semaphore | None = None


def _get_qa_semaphore() -> asyncio.Semaphore:
    """Get or create the QA semaphore for the current event loop."""
    global _qa_semaphore
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    # Recreate if None or bound to a different/closed loop
    if _qa_semaphore is None or loop is not getattr(_qa_semaphore, '_loop', None):
        _qa_semaphore = asyncio.Semaphore(QA_CONCURRENCY_LIMIT)
    return _qa_semaphore


class QACheckResultSchema(BaseModel):
    """Schema for LLM structured output."""
    requirement_id: str
    passed: bool
    confidence: float = Field(ge=0, le=1)
    explanation: str
    severity: Literal["critical", "warning", "info"] = "critical"
    suggestion: str | None = None


class QAReviewSchema(BaseModel):
    """Schema for LLM structured output."""
    overall_passes: bool
    overall_confidence: float = Field(ge=0, le=1)
    overall_feedback: str
    check_results: list[QACheckResultSchema]
    needs_rewrite: bool
    suggested_revisions: list[str] = Field(default_factory=list)


def _build_qa_context(
    element: DraftElement,
    requirements: DraftRequirements,
) -> dict:
    """Build context for QA review template."""
    # Get requirements for this element
    element_reqs = requirements.get_requirements_for_element(element.name)
    
    return {
        "section_name": element.name,
        "section_display_name": element.display_name,
        "draft_content": element.content,
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
    """Convert LLM schema to internal model."""
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


def _enforce_confidence_thresholds(
    schema_result: QAReviewSchema,
    element_reqs: list,
) -> tuple[QAReview, bool, bool]:
    """
    Enforce deterministic pass/fail based on confidence thresholds.
    
    This overrides the LLM's overall_passes with our defined rules:
    - Fail if ANY critical requirement failed
    - Fail if overall_confidence < QA_PASS_THRESHOLD
    - Trigger rewrite if overall_confidence < QA_REWRITE_THRESHOLD
    
    Args:
        schema_result: Raw LLM output
        element_reqs: Requirements for joining is_critical flag
        
    Returns:
        Tuple of (QAReview, passes, needs_rewrite)
    """
    # Build requirement lookup for is_critical
    req_by_id = {r.id: r for r in element_reqs}
    
    # Check for critical failures
    critical_failed = False
    for check in schema_result.check_results:
        req = req_by_id.get(check.requirement_id)
        if req and req.is_critical and not check.passed:
            critical_failed = True
            break
    
    # Determine pass/fail based on our thresholds
    confidence = schema_result.overall_confidence
    
    if critical_failed:
        passes = False
        needs_rewrite = True
    elif confidence < QA_PASS_THRESHOLD:
        passes = False
        needs_rewrite = confidence < QA_REWRITE_THRESHOLD
    else:
        passes = True
        needs_rewrite = False
    
    # Override LLM's decisions with our deterministic rules
    check_results = [
        QACheckResult(
            requirement_id=r.requirement_id,
            passed=r.passed,
            explanation=r.explanation,
            severity=r.severity,
            suggestion=r.suggestion,
        )
        for r in schema_result.check_results
    ]
    
    qa_review = QAReview(
        passes=passes,  # Our decision, not LLM's
        check_results=check_results,
        overall_feedback=schema_result.overall_feedback,
        needs_rewrite=needs_rewrite,  # Our decision
        suggested_revisions=schema_result.suggested_revisions,
    )
    
    return qa_review, passes, needs_rewrite


@traced_node
async def qa_review_node(state: AgentState) -> dict:
    """
    QA review of all prerequisite-ready draft elements (parallel).

    Processes every element whose prerequisites are satisfied and whose status is
    pending/needs_revision/drafted. Runs LLM QA for each in parallel, applies
    results, and returns consolidated messages. The current_element_index is set to
    the first reviewed element (for downstream routing/user approval).
    """
    draft_elements = state.get("draft_elements", [])
    if not draft_elements:
        return {"messages": [AIMessage(content="No elements to review.")]}

    ready_indices = find_ready_indices(draft_elements)
    if not ready_indices:
        return {"messages": [AIMessage(content="No draft elements are ready for QA.")]}

    # Filter out elements with no content (not yet generated)
    ready_indices = [
        idx for idx in ready_indices 
        if DraftElement.model_validate(draft_elements[idx]).content
    ]
    if not ready_indices:
        return {"messages": [AIMessage(content="No drafted elements with content ready for QA.")]}

    reqs_dict = state.get("draft_requirements")
    requirements = DraftRequirements.model_validate(reqs_dict) if reqs_dict else None

    async def _qa_single(idx: int):
        element = DraftElement.model_validate(draft_elements[idx])

        # Skip QA if content unchanged and previously passed (Issue 1.4)
        if (
            element.qa_content_unchanged()
            and element.qa_review
            and element.qa_review.passes
        ):
            logger.info(f"Skipping QA for {element.name}: content unchanged since last pass")
            return idx, element, element.qa_review, 1.0

        # Auto-pass literal-tier sections (Factor 8/9, Other Significant Factors)
        # These use predetermined text that doesn't need LLM validation.
        if get_generation_tier(element.name) == "literal":
            qa_review = QAReview(
                passes=True,
                check_results=[],
                overall_feedback="Predetermined narrative — no QA required",
                needs_rewrite=False,
                suggested_revisions=[],
            )
            element.apply_qa_review(qa_review)
            logger.info(f"Auto-passed QA for literal section: {element.name}")
            return idx, element, qa_review, 1.0

        # Handle no requirements cases - STILL call apply_qa_review for consistency (Issue 1.1)
        if not requirements:
            qa_review = QAReview(
                passes=True,
                check_results=[],
                overall_feedback="No requirements defined for this draft",
                needs_rewrite=False,
                suggested_revisions=[],
            )
            element.apply_qa_review(qa_review)  # FIX: Use apply_qa_review
            return idx, element, qa_review, 1.0

        element_reqs = requirements.get_requirements_for_element(element.name)
        if not element_reqs:
            qa_review = QAReview(
                passes=True,
                check_results=[],
                overall_feedback=f"No specific requirements for {element.display_name}",
                needs_rewrite=False,
                suggested_revisions=[],
            )
            element.apply_qa_review(qa_review)  # FIX: Use apply_qa_review
            return idx, element, qa_review, 1.0

        context = _build_qa_context(element, requirements)
        template = jinja_env.get_template("qa_review.jinja")
        prompt = template.render(**context)

        llm = get_chat_model(temperature=0)

        # Limit concurrent LLM calls (Issue 1.3)
        sem = _get_qa_semaphore()
        async with sem:
            try:
                result, _usage = await traced_structured_llm_call(
                    llm=llm,
                    prompt=prompt,
                    output_schema=QAReviewSchema,
                    node_name=f"qa_review:{element.name}",
                    metadata={"element": element.name},
                )
                
                # Apply deterministic thresholds (Issue 1.2)
                qa_review, passes, needs_rewrite = _enforce_confidence_thresholds(
                    result, element_reqs
                )
                overall_conf = result.overall_confidence
                
                # Log if we overrode the LLM's decision
                if passes != result.overall_passes:
                    logger.info(
                        f"QA threshold override for {element.name}: "
                        f"LLM said passes={result.overall_passes}, "
                        f"thresholds say passes={passes} (conf={overall_conf:.2f})"
                    )
                    
            except Exception as e:
                qa_review = QAReview(
                    passes=False,
                    check_results=[],
                    overall_feedback=f"QA review error: {str(e)}",
                    needs_rewrite=False,
                    suggested_revisions=[],
                )
                overall_conf = 0.0

        element.apply_qa_review(qa_review)
        if not qa_review.passes:
            element.save_to_history(reason="qa_failure")

        return idx, element, qa_review, overall_conf

    results = await asyncio.gather(*[_qa_single(idx) for idx in ready_indices])

    # Invariant: Every reviewed element must have qa_review populated (Issue 1.1)
    for idx, element, qa_review, _ in results:
        assert element.qa_review is not None, (
            f"BUG: Element {element.name} has status {element.status} "
            f"but qa_review is None. This violates our state consistency invariant."
        )

    # Update state with all QA results
    for idx, element, qa_review, _ in results:
        draft_elements[idx] = element.model_dump()

    # Build consolidated messages
    messages: list[AIMessage] = []
    # Prefer the element the user was actively working on (current_element_name),
    # falling back to the first ready index.  This prevents a targeted revision
    # (e.g., Factor 9) from being overshadowed by a lower-index element.
    current_element_name = state.get("current_element_name", "")
    primary_index = ready_indices[0]
    if current_element_name:
        for idx in ready_indices:
            if draft_elements[idx].get("name") == current_element_name:
                primary_index = idx
                break
    # Only the primary element gets a full chat message.  Other elements
    # are visible via element_update in the ProductPanel — flooding the
    # chat with "X ✅ Passed QA" × 9 is noise when a status tracker exists.
    next_prompt = ""
    other_passed = 0
    other_needs_rewrite = 0

    for idx, element, qa_review, conf in results:
        if idx == primary_index:
            # Primary element always gets a chat message
            if qa_review.passes:
                msg = f"**{element.display_name}** passed QA — ready for your review."
            elif element.can_rewrite:
                msg = f"**{element.display_name}** needs revision — rewriting automatically (attempt {element.revision_count + 1})..."
            else:
                msg = f"**{element.display_name}** didn't fully pass QA — please review and provide feedback."
            messages.append(AIMessage(content=msg))
        else:
            # Count non-primary results for summary
            if qa_review.passes:
                other_passed += 1
            elif element.can_rewrite:
                other_needs_rewrite += 1
            else:
                other_passed += 1  # At limit — still shows in panel

    # One-line summary for batch results (if any)
    if other_passed > 0:
        section_word = "section" if other_passed == 1 else "sections"
        messages.append(AIMessage(content=f"{other_passed} other {section_word} also passed QA."))

    return {
        "messages": messages,
        "draft_elements": draft_elements,
        "current_element_index": primary_index,
        "current_element_name": DraftElement.model_validate(draft_elements[primary_index]).name,
        "next_prompt": next_prompt,  # Empty — ProductPanel buttons handle approval
    }


# Keep alias for backwards compatibility with imports
qa_review_node_sync = qa_review_node
