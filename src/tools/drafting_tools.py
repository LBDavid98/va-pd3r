"""Drafting tools for LLM-driven PD section generation.

These tools wrap existing drafting logic from:
- src/nodes/generate_element_node.py (section generation)
- docs/business_rules/drafting_sections.py (section configuration)

ARCHITECTURE NOTE: We wrap existing logic as tools for agent access,
preserving all existing business logic and Jinja2 templates.
Per ADR-006, the LLM decides which tool to call via tool selection.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Literal

from jinja2 import Environment, FileSystemLoader
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from src.config.drafting_sections import SECTION_REGISTRY, get_predetermined_narrative

from src.config.fes_factors import get_does_statements, get_factor_name, get_factor_points
from src.models.draft import DraftElement, QAReview
from src.models.fes import FESEvaluation
from src.models.interview import InterviewData
from src.models.requirements import DraftRequirements
from src.utils.llm import traced_llm_call

logger = logging.getLogger(__name__)

# Setup Jinja environment for templates
TEMPLATES_DIR = Path(__file__).parent.parent / "prompts" / "templates"
jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))


# =============================================================================
# HELPER FUNCTIONS (from generate_element_node.py)
# =============================================================================

def _get_section_config(element_name: str) -> dict:
    """Get section configuration from business rules."""
    return SECTION_REGISTRY.get(element_name, {})


def _extract_grade_num(grade_value: str | None) -> int:
    """Extract numeric grade from value like 'GS-13' or '13'."""
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


def _build_draft_context(
    section_name: str,
    interview_data: InterviewData,
    fes_evaluation: FESEvaluation | None,
    requirements: DraftRequirements | None,
    is_rewrite: bool = False,
    qa_feedback: str = "",
    qa_failures: list | None = None,
) -> dict:
    """Build the context dict for the draft.jinja template.
    
    This is extracted from generate_element_node._build_prompt_context
    and adapted for tool use.
    """
    section_config = _get_section_config(section_name)
    
    # Get display name
    display_name = section_config.get("description", section_name.replace("_", " ").title())
    
    # Basic position info from interview
    context = {
        "section_name": display_name,
        "section_description": section_config.get("description", ""),
        "section_style": section_config.get("style", "narrative"),
        "position_title": interview_data.position_title.value or "Unknown",
        "series": interview_data.series.value or "",
        "grade": _extract_grade_num(interview_data.grade.value),
        "organization": _format_org(interview_data.organization.value),
        "reports_to": interview_data.reports_to.value or "",
        "is_supervisor": interview_data.is_supervisor.value or False,
        "num_supervised": interview_data.num_supervised.value or 0,
        "percent_supervising": interview_data.percent_supervising.value or 0,
        "daily_activities": interview_data.major_duties.value or [],
        "major_duties": interview_data.major_duties.value or [],
        "is_rewrite": is_rewrite,
        "qa_feedback": qa_feedback,
        "qa_failures": qa_failures or [],
    }
    
    # Add factor-specific context if this is an FES factor section
    factor_id = section_config.get("factor_id")
    if factor_id and fes_evaluation:
        context["factor_id"] = factor_id
        
        # Handle combined factors (6_7)
        if factor_id == "6_7":
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
        element_reqs = requirements.get_requirements_for_element(section_name)
        context["requirements"] = element_reqs
    
    return context


async def _generate_section_content(
    section_name: str,
    context: dict,
    is_rewrite: bool = False,
    rewrite_context: dict | None = None,
) -> tuple[str, dict]:
    """Generate section content using LLM.
    
    Returns:
        Tuple of (content, usage_info)
    """
    section_config = _get_section_config(section_name)
    
    # Handle predetermined narratives (factors 8 & 9)
    if section_config.get("style") == "predetermined_narrative":
        content = context.get("predetermined_content", "")
        return content, {"tokens": 0, "predetermined": True}
    
    # Select template
    if is_rewrite and rewrite_context:
        template = jinja_env.get_template("draft_rewrite.jinja")
        context.update(rewrite_context)
    else:
        template = jinja_env.get_template("draft.jinja")
    
    prompt = template.render(**context)
    
    # Use GPT-4o for drafting
    llm = ChatOpenAI(model="gpt-4o", temperature=0.3)
    
    content, usage = await traced_llm_call(
        llm=llm,
        prompt=prompt,
        node_name=f"drafting_tool:{section_name}",
        metadata={"section": section_name, "is_rewrite": is_rewrite},
    )
    
    return content.strip(), usage


# =============================================================================
# DRAFTING TOOLS
# =============================================================================

@tool
def write_section(
    section_name: str,
    interview_data_dict: dict,
    fes_evaluation_dict: dict | None = None,
    requirements_dict: dict | None = None,
) -> str:
    """Write a new PD section using collected interview data and FES evaluation.

    Use this tool to generate a draft for any PD section including:
    - introduction: Opening narrative summarizing the position
    - background: Organizational context and mission alignment
    - duties_overview: Major duties and responsibilities
    - factor_1_knowledge through factor_9_work_environment: FES factor narratives

    The LLM uses Jinja2 templates and collected data to generate compliant content.

    Args:
        section_name: Name of the section to write (e.g., 'introduction', 'factor_1_knowledge')
        interview_data_dict: Collected interview data as dict
        fes_evaluation_dict: FES factor evaluation results (optional, needed for factor sections)
        requirements_dict: Draft requirements (optional)

    Returns:
        Generated section content or error message
    """
    logger.info(f"Tool write_section: {section_name}")
    
    # Validate section exists
    if section_name not in SECTION_REGISTRY:
        valid_sections = list(SECTION_REGISTRY.keys())
        return f"Error: Unknown section '{section_name}'. Valid sections: {valid_sections}"
    
    # Parse input models
    try:
        interview_data = InterviewData.model_validate(interview_data_dict)
    except Exception as e:
        return f"Error parsing interview_data: {e}"
    
    fes_evaluation = None
    if fes_evaluation_dict:
        try:
            fes_evaluation = FESEvaluation.model_validate(fes_evaluation_dict)
        except Exception as e:
            logger.warning(f"Could not parse FES evaluation: {e}")
    
    requirements = None
    if requirements_dict:
        try:
            requirements = DraftRequirements.model_validate(requirements_dict)
        except Exception as e:
            logger.warning(f"Could not parse requirements: {e}")
    
    # Build context
    context = _build_draft_context(
        section_name=section_name,
        interview_data=interview_data,
        fes_evaluation=fes_evaluation,
        requirements=requirements,
    )
    
    # Generate content
    try:
        content, usage = asyncio.get_event_loop().run_until_complete(
            _generate_section_content(section_name, context)
        )
    except RuntimeError:
        # No event loop running - create one
        content, usage = asyncio.run(
            _generate_section_content(section_name, context)
        )
    
    return content


@tool
def revise_section(
    section_name: str,
    current_content: str,
    qa_feedback: str,
    qa_failures: list[str],
    interview_data_dict: dict,
    fes_evaluation_dict: dict | None = None,
    requirements_dict: dict | None = None,
) -> str:
    """Revise a PD section based on QA feedback.

    Use this tool when a section has failed QA and needs to be rewritten.
    Provide the current content and QA feedback so the LLM can improve it.

    Args:
        section_name: Name of the section to revise
        current_content: The current draft content that needs revision
        qa_feedback: Overall feedback from QA review
        qa_failures: List of specific requirements that failed
        interview_data_dict: Collected interview data as dict
        fes_evaluation_dict: FES factor evaluation results (optional)
        requirements_dict: Draft requirements (optional)

    Returns:
        Revised section content or error message
    """
    logger.info(f"Tool revise_section: {section_name}")
    
    # Validate section exists
    if section_name not in SECTION_REGISTRY:
        valid_sections = list(SECTION_REGISTRY.keys())
        return f"Error: Unknown section '{section_name}'. Valid sections: {valid_sections}"
    
    # Parse input models
    try:
        interview_data = InterviewData.model_validate(interview_data_dict)
    except Exception as e:
        return f"Error parsing interview_data: {e}"
    
    fes_evaluation = None
    if fes_evaluation_dict:
        try:
            fes_evaluation = FESEvaluation.model_validate(fes_evaluation_dict)
        except Exception as e:
            logger.warning(f"Could not parse FES evaluation: {e}")
    
    requirements = None
    if requirements_dict:
        try:
            requirements = DraftRequirements.model_validate(requirements_dict)
        except Exception as e:
            logger.warning(f"Could not parse requirements: {e}")
    
    # Build context with QA feedback
    context = _build_draft_context(
        section_name=section_name,
        interview_data=interview_data,
        fes_evaluation=fes_evaluation,
        requirements=requirements,
        is_rewrite=True,
        qa_feedback=qa_feedback,
        qa_failures=qa_failures,
    )
    
    # Rewrite context includes the current draft
    rewrite_context = {
        "current_draft": current_content,
        "previous_attempts": [{"content": current_content, "qa_feedback": qa_feedback}],
    }
    
    # Generate revised content
    try:
        content, usage = asyncio.get_event_loop().run_until_complete(
            _generate_section_content(section_name, context, is_rewrite=True, rewrite_context=rewrite_context)
        )
    except RuntimeError:
        content, usage = asyncio.run(
            _generate_section_content(section_name, context, is_rewrite=True, rewrite_context=rewrite_context)
        )
    
    return content


@tool
def get_section_status(draft_elements_list: list[dict]) -> str:
    """Get the current status of all PD sections.

    Use this tool to check which sections have been drafted, which are pending,
    and which need revision before proceeding.

    Args:
        draft_elements_list: List of DraftElement dicts from state

    Returns:
        Formatted status summary of all sections
    """
    logger.info("Tool get_section_status")
    
    if not draft_elements_list:
        return "No draft elements initialized yet. Start with write_section for 'introduction'."
    
    lines = ["## Section Status", ""]
    
    completed = []
    pending = []
    needs_revision = []
    qa_passed = []
    
    for elem_dict in draft_elements_list:
        try:
            elem = DraftElement.model_validate(elem_dict)
            name = elem.display_name or elem.name
            
            if elem.status == "approved":
                completed.append(name)
            elif elem.status == "qa_passed":
                qa_passed.append(name)
            elif elem.status == "needs_revision":
                needs_revision.append(f"{name} (revision #{elem.revision_count + 1})")
            else:
                pending.append(name)
        except Exception:
            continue
    
    if completed:
        lines.append(f"✅ **Completed**: {', '.join(completed)}")
    if qa_passed:
        lines.append(f"🔍 **Passed QA (awaiting approval)**: {', '.join(qa_passed)}")
    if needs_revision:
        lines.append(f"⚠️ **Needs Revision**: {', '.join(needs_revision)}")
    if pending:
        lines.append(f"⏳ **Pending**: {', '.join(pending)}")
    
    total = len(draft_elements_list)
    done = len(completed) + len(qa_passed)
    lines.extend(["", f"**Progress**: {done}/{total} sections complete"])
    
    return "\n".join(lines)


@tool
def list_available_sections() -> str:
    """List all available PD sections that can be drafted.

    Use this tool to see what sections exist and their drafting order.

    Returns:
        Formatted list of all available sections with descriptions
    """
    logger.info("Tool list_available_sections")
    
    lines = ["## Available PD Sections", ""]
    
    # Group by batch
    batches = {}
    for section_id, config in SECTION_REGISTRY.items():
        batch = config.get("batch", "other")
        if batch not in batches:
            batches[batch] = []
        batches[batch].append((section_id, config))
    
    for batch_name, sections in batches.items():
        lines.append(f"### {batch_name.replace('_', ' ').title()}")
        for section_id, config in sections:
            desc = config.get("description", "No description")
            style = config.get("style", "narrative")
            lines.append(f"- **{section_id}**: {desc} ({style})")
        lines.append("")
    
    return "\n".join(lines)


@tool
def get_section_requirements(
    section_name: str,
    requirements_dict: dict | None = None,
) -> str:
    """Get the specific requirements for a section.

    Use this tool before writing a section to understand what must be included.

    Args:
        section_name: Name of the section
        requirements_dict: Draft requirements (optional)

    Returns:
        Formatted list of requirements for the section
    """
    logger.info(f"Tool get_section_requirements: {section_name}")
    
    if section_name not in SECTION_REGISTRY:
        return f"Error: Unknown section '{section_name}'"
    
    config = SECTION_REGISTRY[section_name]
    lines = [
        f"## Requirements for {section_name}",
        f"**Description**: {config.get('description', 'N/A')}",
        f"**Style**: {config.get('style', 'narrative')}",
        "",
    ]
    
    # Required fields from interview
    requires = config.get("requires", [])
    if requires:
        lines.append("**Required Interview Data**:")
        for req in requires:
            lines.append(f"- {req}")
        lines.append("")
    
    # Factor ID if applicable
    factor_id = config.get("factor_id")
    if factor_id:
        lines.append(f"**FES Factor**: Factor {factor_id}")
        if factor_id in ("8", "9"):
            lines.append("*Note: This factor uses predetermined narrative*")
        lines.append("")
    
    # Requirements from DraftRequirements if provided
    if requirements_dict:
        try:
            requirements = DraftRequirements.model_validate(requirements_dict)
            element_reqs = requirements.get_requirements_for_element(section_name)
            if element_reqs:
                lines.append("**Content Requirements**:")
                for req in element_reqs:
                    critical = "🔴" if req.is_critical else "🟡"
                    exclusion = " [EXCLUDE]" if req.is_exclusion else ""
                    lines.append(f"- {critical}{exclusion} {req.description}")
                    if req.target_content:
                        lines.append(f"  Target concepts: {', '.join(req.target_content[:3])}...")
        except Exception:
            pass
    
    return "\n".join(lines)


# =============================================================================
# TOOL EXPORTS
# =============================================================================

DRAFTING_TOOLS = [
    write_section,
    revise_section,
    get_section_status,
    list_available_sections,
    get_section_requirements,
]
