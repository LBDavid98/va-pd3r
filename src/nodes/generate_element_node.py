"""Draft element generation node.

Generates a single draft element using the unified draft.jinja template.
Uses SECTION_REGISTRY from business rules to determine section-specific prompts.

Implements tiered generation:
- literal: Fixed text, no LLM call (Factor 8/9)
- llm: Full LLM generation (all narrative sections)

Includes error handling that routes to error_handler on LLM/generation failures.
"""

import asyncio
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from src.config.drafting_sections import SECTION_REGISTRY, TARGET_WORD_COUNTS, get_predetermined_narrative, get_generation_tier

from src.config.fes_factors import get_does_statements, get_factor_name, get_factor_points
from src.config.series_templates import get_duty_template
from src.models.draft import DraftElement, find_next_ready_index, find_ready_indices
from src.models.fes import FESEvaluation
from src.models.interview import InterviewData
from src.models.requirements import DraftRequirements
from src.models.state import AgentState
from src.utils.llm import traced_llm_call, traced_node

logger = logging.getLogger(__name__)

# Setup Jinja environment
TEMPLATES_DIR = Path(__file__).parent.parent / "prompts" / "templates"
jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))


def _get_section_config(element_name: str) -> dict:
    """Get section configuration from business rules."""
    return SECTION_REGISTRY.get(element_name, {})


def _build_prompt_context(
    element: DraftElement,
    interview_data: InterviewData,
    fes_evaluation: FESEvaluation | None,
    requirements: DraftRequirements | None,
    is_rewrite: bool = False,
    qa_feedback: str = "",
    qa_failures: list = None,
) -> dict:
    """Build the context dict for the draft.jinja template."""
    section_config = _get_section_config(element.name)
    
    # Basic position info from interview
    context = {
        "section_name": element.display_name,
        "section_description": section_config.get("description", ""),
        "section_style": section_config.get("style", "narrative"),
        "position_title": interview_data.position_title.value or "Unknown",
        "series": interview_data.series.value or "",
        "grade": _extract_grade_num(interview_data.grade.value),
        "organization": _format_org(interview_data.organization.value),
        "reports_to": interview_data.reports_to.value or "",
        "mission_text": interview_data.mission_text.value or "",
        "organization_hierarchy": interview_data.organization_hierarchy.value or [],
        "is_supervisor": interview_data.is_supervisor.value or False,
        "num_supervised": interview_data.num_supervised.value or 0,
        "percent_supervising": interview_data.percent_supervising.value or 0,
        "daily_activities": interview_data.major_duties.value or [],  # Note: using major_duties for daily
        "major_duties": interview_data.major_duties.value or [],
        "is_rewrite": is_rewrite,
        "qa_feedback": qa_feedback,
        "qa_failures": qa_failures or [],
        "target_word_count": TARGET_WORD_COUNTS.get(element.name, 0),
    }

    # Add supervisory interview data for GSSG factor sections
    if element.name.startswith("supervisory_factor_"):
        context["supervised_employees"] = interview_data.supervised_employees.value or {}
        context["f1_program_scope"] = interview_data.f1_program_scope.value
        context["f2_organizational_setting"] = interview_data.f2_organizational_setting.value
        context["f3_supervisory_authorities"] = interview_data.f3_supervisory_authorities.value
        context["f4_key_contacts"] = interview_data.f4_key_contacts.value
        context["f5_subordinate_details"] = interview_data.f5_subordinate_details.value or ""
        context["f6_special_conditions"] = interview_data.f6_special_conditions.value or ""
    
    # Add factor-specific context if this is an FES factor section
    factor_id = section_config.get("factor_id")
    if factor_id and fes_evaluation:
        context["factor_id"] = factor_id
        
        # Handle combined factors (6_7)
        if factor_id == "6_7":
            # Get both factors
            factor_6 = fes_evaluation.get_factor(6)
            factor_7 = fes_evaluation.get_factor(7)
            does_6 = factor_6.does if factor_6 else []
            does_7 = factor_7.does if factor_7 else []
            context["does_statements"] = does_6 + does_7
            context["factor_level"] = f"6-{factor_6.level if factor_6 else '?'} / 7-{factor_7.level if factor_7 else '?'}"
            context["factor_points"] = (factor_6.points if factor_6 else 0) + (factor_7.points if factor_7 else 0)
        elif factor_id in ("8", "9"):
            # Predetermined narratives
            default_level = section_config.get("default_level", f"{factor_id}-1")
            level_num = default_level.split("-")[1] if "-" in default_level else "1"
            context["predetermined_content"] = get_predetermined_narrative(factor_id, level_num)
        else:
            # Regular factor (1-5)
            factor_num = int(factor_id)
            factor = fes_evaluation.get_factor(factor_num)
            if factor:
                context["does_statements"] = factor.does
                context["factor_level"] = factor.level_code
                context["factor_points"] = factor.points
    
    # Add duty template if series-specific
    if requirements and requirements.duty_template:
        context["duty_template"] = requirements.duty_template
    
    # Add requirements for this element
    if requirements:
        element_reqs = requirements.get_requirements_for_element(element.name)
        context["requirements"] = element_reqs
    
    return context


def _extract_grade_num(grade_value: str | None) -> int:
    """Extract numeric grade from value."""
    if not grade_value:
        return 0
    cleaned = str(grade_value).upper().replace("GS-", "").replace("GS", "").strip()
    try:
        return int(cleaned)
    except ValueError:
        return 0


def _format_org(org_value) -> str:
    """Format organization value for display."""
    if not org_value:
        return ""
    if isinstance(org_value, list):
        return " > ".join(org_value)
    return str(org_value)


@traced_node
async def generate_element_node(state: AgentState) -> dict:
    """
    Generate a single draft element using LLM.

    Uses the unified draft.jinja template with section-specific context.
    Includes error handling that routes to error_handler on LLM failures.

    Args:
        state: Current agent state

    Returns:
        State update with generated content, or error state on failure
    """
    from src.exceptions import LLMException
    
    def _format_error(error: Exception, element_name: str = "") -> str:
        """Format an exception for the error handler."""
        context = f" (element: {element_name})" if element_name else ""
        return f"generate_element: {type(error).__name__}: {str(error)}{context}"
    
    # Get current element and ensure prerequisites are satisfied
    element_index = state.get("current_element_index", 0)
    draft_elements = state.get("draft_elements", [])
    state_updates: dict = {}

    def _merge(payload: dict) -> dict:
        if state_updates:
            payload.update(state_updates)
        return payload
    
    if not draft_elements:
        return _merge({
            "messages": [AIMessage(content="No more elements to draft.")],
            "phase": "review",
        })

    ready_indices = find_ready_indices(draft_elements)
    if not ready_indices:
        # Check if all elements are done (qa_passed/approved) vs waiting on prereqs
        all_done = all(
            DraftElement.model_validate(e).status in {"qa_passed", "approved"}
            for e in draft_elements
        )
        if all_done:
            return _merge({
                "messages": [AIMessage(content="All sections have been drafted and reviewed.")],
                "phase": "review",
            })
        return _merge({
            "messages": [AIMessage(content="No draft elements are ready based on prerequisites.")],
            "next_prompt": "Waiting for required sections to be drafted...",
        })

    if element_index >= len(draft_elements) or element_index not in ready_indices:
        element_index = ready_indices[0]
        state_updates["current_element_index"] = element_index
    
    # Only generate elements that actually need generation (pending or needs_revision).
    # Skip "drafted" elements — they were already generated (e.g. by batch) and
    # should go through QA, not be regenerated.
    ready_to_generate = [
        idx for idx in ready_indices
        if draft_elements[idx].get("status") in {"pending", "needs_revision"}
    ]
    if not ready_to_generate:
        # All ready elements are already drafted — move on to QA/user
        primary = DraftElement.model_validate(draft_elements[element_index])
        return _merge({
            "messages": [AIMessage(content=f"**{primary.display_name}** is ready for review.")],
            "draft_elements": draft_elements,
            "next_prompt": "Running QA review...",
        })

    async def _generate_single(idx: int) -> tuple:
        """
        Generate a single element based on its generation tier.

        Tiers:
        - literal: Fixed text (Factor 8/9), no LLM call
        - llm: Full LLM generation (all narrative sections)

        Returns: (elem, content, is_rewrite, is_non_llm, error)
        """
        elem_dict = draft_elements[idx]
        elem = DraftElement.model_validate(elem_dict)
        
        # Get interview data for all tiers
        interview_data_local = InterviewData.model_validate(state.get("interview_data", {}))

        # Get FES evaluation
        fes_dict_local = state.get("fes_evaluation")
        fes_eval_local = FESEvaluation.model_validate(fes_dict_local) if fes_dict_local else None

        # Get requirements
        reqs_dict_local = state.get("draft_requirements")
        reqs_local = DraftRequirements.model_validate(reqs_dict_local) if reqs_dict_local else None

        # Element is a rewrite if it previously failed QA (needs_revision status)
        # This correctly increments revision_count to enforce rewrite limits
        is_rewrite_local = elem.status == "needs_revision"
        qa_feedback_local = ""
        qa_failures_local = []

        if is_rewrite_local and elem.qa_review:
            qa_feedback_local = elem.qa_review.overall_feedback
            qa_failures_local = [r for r in elem.qa_review.check_results if not r.passed]

        # Determine generation tier
        generation_tier = get_generation_tier(elem.name)
        section_config_local = _get_section_config(elem.name)
        
        # TIER 1: Literal generation (Factor 8/9, Other Significant Factors)
        # Fixed text from predetermined narratives - no LLM call
        if generation_tier == "literal" or section_config_local.get("style") == "predetermined_narrative":
            if elem.name == "other_significant_factors":
                # Other Significant Factors uses supervisory variant when applicable
                is_sup = interview_data_local.is_supervisor.value or False
                variant = "supervisory" if is_sup else "default"
                content_local = get_predetermined_narrative("other_significant_factors", variant)
            else:
                factor_id = section_config_local.get("factor_id")
                default_level = section_config_local.get("default_level", f"{factor_id}-1")
                level_num = default_level.split("-")[1] if "-" in default_level else "1"
                content_local = get_predetermined_narrative(factor_id, level_num)
            elem.update_content(content_local, is_rewrite=is_rewrite_local)
            draft_elements[idx] = elem.model_dump()
            logger.debug(f"Tier 'literal': Generated {elem.name} without LLM")
            return elem, content_local, is_rewrite_local, True, None
        
        # TIER 2: LLM generation (duties, factors 1-7, intro, background, rewrites)
        # Full LLM generation with prompt template
        context_local = _build_prompt_context(
            element=elem,
            interview_data=interview_data_local,
            fes_evaluation=fes_eval_local,
            requirements=reqs_local,
            is_rewrite=is_rewrite_local,
            qa_feedback=qa_feedback_local,
            qa_failures=qa_failures_local,
        )

        if is_rewrite_local and elem.draft_history:
            template_local = jinja_env.get_template("draft_rewrite.jinja")
            rewrite_context_local = elem.get_rewrite_context()
            context_local.update(rewrite_context_local)
        else:
            # Use section-specific template if available, fall back to generic
            section_template = f"draft_{elem.name}.jinja"
            try:
                template_local = jinja_env.get_template(section_template)
                logger.debug(f"Using section-specific template: {section_template}")
            except Exception:
                template_local = jinja_env.get_template("draft.jinja")

        prompt_local = template_local.render(**context_local)
        from src.utils import get_model_for_attempt
        llm_local, _model_name_local = get_model_for_attempt(elem.attempt_number)
        content_local, _usage = await traced_llm_call(
            llm=llm_local,
            prompt=prompt_local,
            node_name=f"generate_element:{elem.name}",
            metadata={"element": elem.name, "is_rewrite": is_rewrite_local, "tier": "llm"},
        )
        content_local = content_local.strip()
        elem.update_content(content_local, is_rewrite=is_rewrite_local)
        draft_elements[idx] = elem.model_dump()
        logger.debug(f"Tier 'llm': Generated {elem.name} via LLM")
        return elem, content_local, is_rewrite_local, False, None

    # Run all ready generations in parallel with error handling
    try:
        results = await asyncio.gather(
            *[_generate_single(idx) for idx in ready_to_generate],
            return_exceptions=True  # Capture exceptions instead of raising
        )
    except Exception as e:
        # Unexpected error in gather itself
        logger.error(f"Unexpected error in parallel generation: {e}")
        return _merge({
            "last_error": _format_error(e),
            "messages": [AIMessage(content="An unexpected error occurred during generation.")],
        })
    
    # Check for errors in results
    successful_results = []
    first_error = None
    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            element_name = draft_elements[ready_to_generate[idx]].get("name", "unknown")
            logger.error(f"Error generating element {element_name}: {result}")
            if first_error is None:
                first_error = (result, element_name)
        else:
            successful_results.append(result)
    
    # If all generations failed, route to error handler
    if not successful_results and first_error:
        error, element_name = first_error
        return _merge({
            "last_error": _format_error(error, element_name),
            "messages": [AIMessage(content=f"I encountered an error generating the {element_name.replace('_', ' ')} section.")],
        })

    # Build messages: show detailed content for the primary element, brief summaries for others
    messages: list[AIMessage] = []
    primary_elem: DraftElement | None = None
    primary_content = ""
    for result in successful_results:
        elem, content, is_rewrite_flag, is_predetermined, error = result
        if error:
            # Skip errored elements (already logged)
            continue
        if primary_elem is None or elem.name == draft_elements[element_index]["name"]:
            primary_elem = elem
            primary_content = content
        else:
            tag = "updated draft" if is_rewrite_flag else "draft"
            messages.append(
                AIMessage(
                    content=f"Generated {tag} for **{elem.display_name}** (queued for QA)."
                )
            )

    # Ensure primary message is first — content lives in the product panel,
    # so the chat message is just a short notification
    if primary_elem:
        from src.utils.personality import get_completion
        action_phrase = "Here's an updated draft for" if primary_elem.revision_count > 0 else f"{get_completion()}"
        messages.insert(0, AIMessage(
            content=f"{action_phrase} **{primary_elem.display_name}** — review it in the draft panel."
        ))
        state_updates.setdefault("current_element_name", primary_elem.name)

    # If nothing was generated (should not happen), fallback
    if not messages:
        messages = [AIMessage(content="Drafting completed.")]
    
    return _merge({
        "messages": messages,
        "draft_elements": draft_elements,
        "next_prompt": "Running QA review...",
    })


# Keep alias for backwards compatibility with imports
generate_element_node_sync = generate_element_node
