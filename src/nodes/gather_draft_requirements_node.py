"""Requirements gathering node for draft generation.

Combines FES evaluation, series-specific duty templates, and interview data
to build a comprehensive set of requirements for the position description draft.
"""

from langchain_core.messages import AIMessage

from src.config.fes_factors import get_does_not_statements, parse_grade_number
from src.config.series_templates import get_duty_template
from src.constants import MAX_DRAFTS
from src.models.draft import (
    DRAFT_ELEMENT_NAMES,
    create_all_draft_elements,
    find_next_ready_index,
    find_ready_indices,
)
from src.models.duties import SeriesDutyTemplate
from src.models.fes import FESEvaluation
from src.models.interview import InterviewData
from src.models.requirements import DraftRequirement, DraftRequirements
from src.models.state import AgentState
from src.utils.llm import traced_node


def _build_fes_requirements(fes_evaluation: FESEvaluation) -> list[DraftRequirement]:
    """
    Build requirements from FES evaluation.

    Each "does" statement becomes an INCLUSION requirement that must appear.
    Each "does_not" statement becomes an EXCLUSION requirement that must NOT appear.
    """
    requirements = []

    # Map factor numbers to element names
    factor_element_map = {
        1: "factor_1_knowledge",
        2: "factor_2_supervisory_controls",
        3: "factor_3_guidelines",
        4: "factor_4_complexity",
        5: "factor_5_scope_effect",
        6: "factor_6_7_contacts",
        7: "factor_6_7_contacts",
        8: "factor_8_physical_demands",
        9: "factor_9_work_environment",
    }

    for factor in fes_evaluation.all_factors:
        element_name = factor_element_map.get(
            int(factor.factor_num) if isinstance(factor.factor_num, str) else factor.factor_num,
            "factor_6_7_contacts"
        )

        # INCLUSION requirements: concepts that SHOULD appear (evaluated by LLM)
        for idx, does_statement in enumerate(factor.does):
            req_id = f"fes_{factor.factor_num}_{factor.level_code}_{idx}"
            requirements.append(
                DraftRequirement(
                    id=req_id,
                    description=f"Include: {does_statement[:80]}..."
                    if len(does_statement) > 80
                    else f"Include: {does_statement}",
                    element_name=element_name,
                    check_type="semantic",
                    # target_content for LLM to evaluate (NOT keyword matching)
                    keywords=[does_statement],  # alias for target_content
                    is_exclusion=False,  # Concept should be present
                    is_critical=True,
                    source=f"FES Factor {factor.factor_num} Level {factor.level_code}",
                )
            )

        # EXCLUSION requirements: concepts that SHOULD NOT appear (evaluated by LLM)
        # Get does_not from FES data (may be empty for most factors)
        factor_num = int(factor.factor_num) if isinstance(factor.factor_num, str) else factor.factor_num
        does_not_statements = get_does_not_statements(factor_num, factor.level_code)
        
        for idx, does_not_statement in enumerate(does_not_statements):
            req_id = f"fes_{factor.factor_num}_{factor.level_code}_not_{idx}"
            requirements.append(
                DraftRequirement(
                    id=req_id,
                    description=f"Exclude: {does_not_statement[:80]}..."
                    if len(does_not_statement) > 80
                    else f"Exclude: {does_not_statement}",
                    element_name=element_name,
                    check_type="semantic",
                    # target_content for LLM to evaluate absence (NOT keyword matching)
                    keywords=[does_not_statement],  # alias for target_content
                    is_exclusion=True,  # Concept should be absent
                    is_critical=True,  # Grade-inappropriate language is critical
                    source=f"FES Factor {factor.factor_num} Level {factor.level_code} exclusion",
                )
            )

    return requirements


def _build_duty_requirements(duty_template: SeriesDutyTemplate) -> list[DraftRequirement]:
    """
    Build requirements from series-specific duty template.

    Each duty section becomes a requirement with weight constraints.
    """
    requirements = []

    for idx, section in enumerate(duty_template.duty_sections):
        req_id = f"duty_{duty_template.series}_{duty_template.grade}_{idx}"
        requirements.append(
            DraftRequirement(
                id=req_id,
                description=f"Major Duties must include '{section.title}' section "
                f"({section.min_percent}-{section.max_percent}%)",
                element_name="major_duties",
                check_type="weight",
                keywords=[section.title],
                is_critical=True,
                source=f"Duty Template {duty_template.series}-{duty_template.grade}",
                min_weight=section.min_percent,
                max_weight=section.max_percent,
            )
        )

    # Add overall weight sum requirement
    requirements.append(
        DraftRequirement(
            id=f"duty_{duty_template.series}_{duty_template.grade}_total",
            description="Major Duties section weights must sum to 100%",
            element_name="major_duties",
            check_type="weight",
            keywords=[],
            is_critical=True,
            source=f"Duty Template {duty_template.series}-{duty_template.grade}",
        )
    )

    return requirements


def _build_structural_requirements(is_supervisor: bool) -> list[DraftRequirement]:
    """Build structural requirements for the draft."""
    requirements = []

    # Introduction must include basic position information
    requirements.append(
        DraftRequirement(
            id="struct_intro_title",
            description="Introduction must include position title",
            element_name="introduction",
            check_type="structure",
            keywords=["position", "title"],
            is_critical=True,
            source="Structure Requirements",
        )
    )

    requirements.append(
        DraftRequirement(
            id="struct_intro_org",
            description="Introduction must include organization",
            element_name="introduction",
            check_type="structure",
            keywords=["organization", "department", "office"],
            is_critical=True,
            source="Structure Requirements",
        )
    )

    # Supervisory requirements if applicable
    if is_supervisor:
        requirements.append(
            DraftRequirement(
                id="struct_supervisory",
                description="Must include supervisory responsibilities",
                element_name="major_duties",
                check_type="keyword",
                keywords=["supervise", "supervision", "supervisory", "manage staff"],
                is_critical=True,
                source="Supervisory Position Requirements",
            )
        )

    return requirements


@traced_node
def gather_draft_requirements_node(state: AgentState) -> dict:
    """
    Gather all requirements for draft generation.

    Combines:
    - FES evaluation requirements (does statements)
    - Series-specific duty template requirements
    - Structural requirements

    Args:
        state: Current agent state with fes_evaluation and interview_data

    Returns:
        State update with draft_requirements and draft_elements initialized
    """
    # Get FES evaluation
    fes_dict = state.get("fes_evaluation")
    if not fes_dict:
        return {
            "messages": [
                AIMessage(
                    content="I need to evaluate FES factors before gathering requirements."
                )
            ],
            "next_prompt": "Let me evaluate the FES factors first...",
        }

    fes_evaluation = FESEvaluation.model_validate(fes_dict)

    # Get interview data for series and supervisory status
    interview_dict = state.get("interview_data", {})
    interview_data = InterviewData.model_validate(interview_dict) if interview_dict else None

    series = None
    grade_num = fes_evaluation.grade_num
    is_supervisor = False

    if interview_data:
        if interview_data.series.is_set:
            series = interview_data.series.value
        if interview_data.is_supervisor.is_set:
            is_supervisor = interview_data.is_supervisor.value or False

    # Build requirements from all sources
    all_requirements: list[DraftRequirement] = []

    # 1. FES requirements
    fes_reqs = _build_fes_requirements(fes_evaluation)
    all_requirements.extend(fes_reqs)

    # 2. Series-specific duty requirements (if template exists)
    duty_template = None
    if series:
        duty_template = get_duty_template(series, grade_num)
        if duty_template:
            duty_reqs = _build_duty_requirements(duty_template)
            all_requirements.extend(duty_reqs)

    # 3. Structural requirements
    struct_reqs = _build_structural_requirements(is_supervisor)
    all_requirements.extend(struct_reqs)

    # Build DraftRequirements model
    draft_requirements = DraftRequirements(
        requirements=all_requirements,
        fes_evaluation=fes_evaluation,
        duty_template=duty_template,
        series=series,
        grade=grade_num,
        is_supervisor=is_supervisor,
    )

    # Initialize draft elements (includes supervisory factors if is_supervisor=True)
    draft_elements = create_all_draft_elements(is_supervisor=is_supervisor)

    # Apply MAX_DRAFTS limit if set (0 = no limit)
    if MAX_DRAFTS > 0:
        draft_elements = draft_elements[:MAX_DRAFTS]

    # Determine first ready element based on prerequisites
    draft_element_dicts = [elem.model_dump() for elem in draft_elements]
    ready_indices = find_ready_indices(draft_element_dicts)
    start_index = ready_indices[0] if ready_indices else 0
    start_element = draft_elements[start_index] if draft_elements else None

    # Build the drafting preamble message
    preamble_lines = [
        "🎉 **Great! We're ready to start writing.**",
        "",
        "A position description consists of the following sections:",
    ]
    
    # List all elements that will be generated
    for elem in draft_elements:
        preamble_lines.append(f"  • {elem.display_name}")
    
    # Add note about supervisory factors if applicable
    if is_supervisor:
        preamble_lines.append("")
        preamble_lines.append("*(Including supervisory factors since this is a supervisory position)*")
    
    if start_element:
        preamble_lines.extend([
            "",
            f"I'll draft each section one at a time for your review. "
            f"That's **{len(draft_elements)} sections** total.",
        ])
    else:
        preamble_lines.append("\nNo draft sections found.")

    preamble = "\n".join(preamble_lines)

    return {
        "messages": [AIMessage(content=preamble)],
        "draft_requirements": draft_requirements.model_dump(),
        "draft_elements": draft_element_dicts,
        "current_element_index": start_index,
        "current_element_name": start_element.name if start_element else None,
        "phase": "drafting",
        "next_prompt": "",
    }


def get_requirements_summary(state: AgentState) -> str | None:
    """
    Get a summary of draft requirements from state.

    Utility function for other nodes.

    Args:
        state: Current agent state

    Returns:
        Summary string or None if no requirements
    """
    reqs_dict = state.get("draft_requirements")
    if not reqs_dict:
        return None

    reqs = DraftRequirements.model_validate(reqs_dict)
    return reqs.to_summary()
