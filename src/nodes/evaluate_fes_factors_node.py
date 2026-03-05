"""FES evaluation node for determining factor levels based on grade.

This node takes the interview data (specifically the grade) and looks up
the appropriate FES factor levels for that grade. All "does" statements
are expanded from the business rules.
"""

from langchain_core.messages import AIMessage

from src.config.fes_factors import evaluate_fes_for_grade, parse_grade_number
from src.models.interview import InterviewData
from src.models.state import AgentState
from src.utils.llm import traced_node
from src.utils.state_compactor import compact_after_interview


@traced_node
def evaluate_fes_factors_node(state: AgentState) -> dict:
    """
    Evaluate FES factors based on the target grade.

    Looks up the appropriate factor levels for the grade and builds
    a complete FESEvaluation with all 'does' statements expanded.

    Args:
        state: Current agent state with interview_data containing grade

    Returns:
        State update with fes_evaluation populated
    """
    # Get interview data
    interview_dict = state.get("interview_data", {})
    if not interview_dict:
        return {
            "messages": [
                AIMessage(
                    content="I need to complete the interview before evaluating FES factors."
                )
            ],
            "next_prompt": "Let's continue with the interview first.",
        }

    # Deserialize interview data
    interview_data = InterviewData.model_validate(interview_dict)

    # Get the grade from interview
    grade_element = interview_data.grade
    if not grade_element.is_set:
        return {
            "messages": [
                AIMessage(
                    content="I need to know the target grade to evaluate FES factors."
                )
            ],
            "next_prompt": "What is the target GS grade for this position?",
        }

    # Parse grade to number
    grade_num = parse_grade_number(grade_element.value)
    if grade_num is None:
        return {
            "messages": [
                AIMessage(
                    content=f"I couldn't parse the grade '{grade_element.value}'. "
                    "Please provide a valid GS grade (9-15)."
                )
            ],
            "next_prompt": "What is the target GS grade for this position?",
        }

    # Evaluate FES for this grade
    fes_evaluation = evaluate_fes_for_grade(grade_num)
    if fes_evaluation is None:
        return {
            "messages": [
                AIMessage(
                    content=f"I don't have FES factor data for GS-{grade_num}. "
                    "This tool supports grades 9-15."
                )
            ],
            "next_prompt": "Please provide a grade between 9 and 15.",
        }

    # Build summary message
    factor_count = len(fes_evaluation.all_factors)
    primary_count = len(fes_evaluation.primary_factors)
    other_count = len(fes_evaluation.other_significant_factors)

    summary_lines = [
        f"✓ FES evaluation complete for GS-{grade_num}:",
        f"  • Total points: {fes_evaluation.total_points}",
        f"  • Primary factors (1-5): {primary_count}",
        f"  • Other significant factors (6-9): {other_count}",
        "",
        "Primary factor levels:",
    ]

    for factor in fes_evaluation.primary_factors:
        summary_lines.append(f"  • {factor.factor_name}: Level {factor.level_code}")

    summary_lines.append("")
    summary_lines.append("Other significant factor levels:")
    for factor in fes_evaluation.other_significant_factors:
        summary_lines.append(f"  • {factor.factor_name}: Level {factor.level_code}")

    summary = "\n".join(summary_lines)

    # Compact transient interview fields now that interview is complete
    compaction_updates = compact_after_interview(state)

    result = {
        "messages": [AIMessage(content=summary)],
        "fes_evaluation": fes_evaluation.model_dump(),
        "phase": "requirements",
        "next_prompt": "Now let me gather the draft requirements...",
    }
    result.update(compaction_updates)
    return result


def get_fes_summary(state: AgentState) -> str | None:
    """
    Get a summary of the FES evaluation from state.

    Utility function for other nodes to access FES summary.

    Args:
        state: Current agent state

    Returns:
        Summary string or None if no evaluation
    """
    fes_dict = state.get("fes_evaluation")
    if not fes_dict:
        return None

    from src.models.fes import FESEvaluation
    fes = FESEvaluation.model_validate(fes_dict)

    lines = [f"FES Evaluation for {fes.grade}:"]
    for factor in fes.all_factors:
        lines.append(f"  Factor {factor.factor_num} ({factor.factor_name}): Level {factor.level_code}")

    return "\n".join(lines)
