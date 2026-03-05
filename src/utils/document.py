"""Document assembly utilities for position descriptions.

Functions for assembling all draft elements into a final document,
creating review summaries, and formatting for output.
"""

from src.models.draft import (
    DRAFT_ELEMENT_DISPLAY_NAMES,
    DRAFT_ELEMENT_NAMES,
    DraftElement,
)
from src.models.interview import InterviewData


def assemble_final_document(
    draft_elements: list[dict],
    interview_data: dict | None = None,
) -> str:
    """
    Assemble all draft elements into a final position description document.

    Combines all drafted sections into a cohesive document with proper
    formatting and section headers.

    Args:
        draft_elements: List of serialized DraftElement dicts
        interview_data: Optional interview data for header information

    Returns:
        Complete position description as formatted markdown string
    """
    if not draft_elements:
        return "No draft elements to assemble."

    lines: list[str] = []

    # Add header if interview data available
    if interview_data:
        interview = InterviewData.model_validate(interview_data)
        lines.extend(_build_document_header(interview))
        lines.append("")

    # Process each element in order
    for element_dict in draft_elements:
        element = DraftElement.model_validate(element_dict)

        # Skip elements without content
        if not element.content:
            continue

        # Add section header
        lines.append(f"## {element.display_name}")
        lines.append("")

        # Add content
        lines.append(element.content)
        lines.append("")

    return "\n".join(lines)


def _build_document_header(interview: InterviewData) -> list[str]:
    """
    Build the OF-8 style document header from interview data.

    Args:
        interview: The InterviewData instance

    Returns:
        List of header lines
    """
    from datetime import date

    lines = ["# Position Description — OF-8", ""]

    # Position title
    if interview.position_title.is_set:
        lines.append(f"**1. Position Title:** {interview.position_title.value}")

    # Classification line
    series = interview.series.value if interview.series.is_set else None
    grade = interview.grade.value if interview.grade.is_set else None
    if series or grade:
        lines.append(
            f"**2. Pay Plan:** GS &nbsp; **3. Series:** {series or 'TBD'} &nbsp; "
            f"**4. Grade:** {grade or 'TBD'}"
        )

    # Organization
    org_data = (interview.organization_hierarchy if interview.organization_hierarchy.is_set
                else interview.organization if interview.organization.is_set else None)
    if org_data and org_data.is_set:
        org = org_data.value
        org_str = " / ".join(org) if isinstance(org, list) else str(org)
        lines.append(f"**5. Employing Department / Agency:** {org_str}")

    # Reports to
    if interview.reports_to.is_set:
        lines.append(f"**6. Reports To:** {interview.reports_to.value}")

    # Supervisory + FLSA
    if interview.is_supervisor.is_set:
        sup = "Supervisory" if interview.is_supervisor.value else "Non-Supervisory"
        flsa = "Exempt" if interview.is_supervisor.value else "Nonexempt"
        lines.append(f"**7. Supervisory Status:** {sup} &nbsp; **8. FLSA Status:** {flsa}")

        if interview.is_supervisor.value:
            if interview.num_supervised.is_set:
                lines.append(f"**Employees Supervised:** {interview.num_supervised.value}")
            if interview.percent_supervising.is_set:
                lines.append(f"**% Time Supervising:** {interview.percent_supervising.value}%")

    # Position sensitivity (derived from grade)
    if grade:
        try:
            grade_num = int(str(grade).replace("GS-", "").strip())
            sensitivity = "Noncritical-Sensitive" if grade_num >= 13 else "Non-Sensitive"
            lines.append(f"**9. Position Sensitivity:** {sensitivity}")
        except ValueError:
            pass

    # Date
    lines.append(f"**13. Date:** {date.today().strftime('%m/%d/%Y')}")

    lines.append("")
    lines.append("---")

    return lines


def create_review_summary(
    draft_elements: list[dict],
    interview_data: dict | None = None,
) -> str:
    """
    Create a summary for final review before export.

    This provides a brief overview of the document with element status
    and any notes for the user.

    Args:
        draft_elements: List of serialized DraftElement dicts
        interview_data: Optional interview data for context

    Returns:
        Review summary string
    """
    if not draft_elements:
        return "No draft elements available for review."

    lines = ["## Position Description Review", ""]

    # Document stats
    total = len(draft_elements)
    approved = sum(
        1 for d in draft_elements
        if DraftElement.model_validate(d).status == "approved"
    )
    qa_passed = sum(
        1 for d in draft_elements
        if DraftElement.model_validate(d).status == "qa_passed"
    )

    lines.append(f"**Total Sections:** {total}")
    lines.append(f"**Approved:** {approved}")
    lines.append(f"**QA Passed:** {qa_passed}")
    lines.append("")

    # Brief status of each element
    lines.append("### Section Status")
    lines.append("")

    status_icons = {
        "approved": "✅",
        "qa_passed": "✓",
        "drafted": "📝",
        "pending": "⏳",
        "needs_revision": "⚠️",
    }

    for element_dict in draft_elements:
        element = DraftElement.model_validate(element_dict)
        icon = status_icons.get(element.status, "❓")
        lines.append(f"- {icon} **{element.display_name}**: {element.status}")

    lines.append("")

    # Add interview summary if available
    if interview_data:
        interview = InterviewData.model_validate(interview_data)
        lines.append("### Position Summary")
        lines.append("")
        if interview.position_title.is_set:
            lines.append(f"- **Title:** {interview.position_title.value}")
        if interview.series.is_set and interview.grade.is_set:
            lines.append(f"- **Classification:** {interview.series.value}-{interview.grade.value}")
        if interview.organization.is_set:
            org = interview.organization.value
            if isinstance(org, list):
                lines.append(f"- **Organization:** {' / '.join(org)}")
            else:
                lines.append(f"- **Organization:** {org}")
        lines.append("")

    return "\n".join(lines)


def get_element_by_name(
    draft_elements: list[dict],
    element_name: str,
) -> tuple[int, DraftElement | None]:
    """
    Find a draft element by name.

    Args:
        draft_elements: List of serialized DraftElement dicts
        element_name: Name of the element to find (can be partial match)

    Returns:
        Tuple of (index, DraftElement) or (-1, None) if not found
    """
    element_name_lower = element_name.lower().replace(" ", "_")

    for idx, element_dict in enumerate(draft_elements):
        element = DraftElement.model_validate(element_dict)

        # Exact match on name
        if element.name.lower() == element_name_lower:
            return idx, element

        # Match on display name
        if element.display_name.lower() == element_name.lower():
            return idx, element

        # Partial match on name
        if element_name_lower in element.name.lower():
            return idx, element

        # Partial match on display name
        if element_name.lower() in element.display_name.lower():
            return idx, element

    return -1, None


def get_supervisory_elements() -> list[str]:
    """
    Get the list of supervisory-specific element names.

    These elements are only included for supervisory positions.

    Returns:
        List of element names for supervisory positions
    """
    # For supervisory positions, we add specific elements
    # Currently this is handled implicitly, but could be extended
    return [
        "supervisory_controls",
        "employee_development",
    ]


def should_include_supervisory_elements(interview_data: dict | None) -> bool:
    """
    Determine if supervisory elements should be included.

    Args:
        interview_data: Serialized interview data

    Returns:
        True if position is supervisory and elements should be included
    """
    if not interview_data:
        return False

    interview = InterviewData.model_validate(interview_data)
    return interview.is_supervisor.is_set and interview.is_supervisor.value is True


def format_element_for_display(element: DraftElement) -> str:
    """
    Format a single draft element for user display during review.

    Args:
        element: The draft element to format

    Returns:
        Formatted string for display
    """
    lines = [
        f"### {element.display_name}",
        "",
        element.content,
        "",
    ]

    # Add status info if not approved
    if element.status != "approved":
        lines.append(f"*Status: {element.status}*")

    # Add QA notes if any
    if element.qa_notes:
        lines.append("")
        lines.append("*QA Notes:*")
        for note in element.qa_notes:
            lines.append(f"- {note}")

    return "\n".join(lines)


def get_all_element_names() -> list[str]:
    """
    Get the complete list of draft element names in order.

    Returns:
        List of element names
    """
    return DRAFT_ELEMENT_NAMES.copy()


def get_element_display_name(element_name: str) -> str:
    """
    Get the display name for an element.

    Args:
        element_name: Internal element name

    Returns:
        Human-readable display name
    """
    return DRAFT_ELEMENT_DISPLAY_NAMES.get(
        element_name,
        element_name.replace("_", " ").title()
    )
