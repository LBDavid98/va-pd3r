"""Procedural generators for tiered PD section generation.

This module provides template-based generation for sections that don't require
full LLM synthesis. These generators use interview data to fill structured templates,
reducing cost and latency while maintaining quality.

Generation Tiers:
- literal: Fixed text, no computation (Factor 8, Factor 9)
- procedural: Template + interview data (introduction, background)
- llm: Full LLM generation (duties, factors 1-7)
"""

import logging
from typing import Any

from src.models.interview import InterviewData

logger = logging.getLogger(__name__)


def generate_introduction(interview_data: InterviewData) -> str:
    """
    Generate introduction section using procedural template.
    
    Uses interview data to construct a consistent opening narrative
    without requiring an LLM call.
    
    Args:
        interview_data: Collected interview responses
        
    Returns:
        Generated introduction text
    """
    position_title = interview_data.position_title.value or "this position"
    series = interview_data.series.value or ""
    grade = _extract_grade_display(interview_data.grade.value)
    org_hierarchy = interview_data.organization_hierarchy.value or interview_data.organization.value or []
    reports_to = interview_data.reports_to.value or "senior leadership"
    is_supervisor = interview_data.is_supervisor.value or False
    num_supervised = interview_data.num_supervised.value or 0
    percent_supervising = interview_data.percent_supervising.value or 0
    major_duties = interview_data.major_duties.value or []
    
    # Build organization context
    if org_hierarchy:
        if len(org_hierarchy) >= 2:
            org_unit = org_hierarchy[-1]
            parent_org = org_hierarchy[0]
            org_phrase = f"the {org_unit} within {parent_org}"
        else:
            org_phrase = org_hierarchy[0]
    else:
        org_phrase = "the organization"
    
    # Build series/grade identifier
    if series and grade:
        position_id = f"{position_title}, {series}-{grade}"
    elif grade:
        position_id = f"{position_title}, GS-{grade}"
    else:
        position_id = position_title
    
    # Build primary duty phrase
    if major_duties:
        primary_duty = major_duties[0].lower()
        if not primary_duty.endswith('.'):
            primary_duty = primary_duty.rstrip('.')
        duty_phrase = f"responsible for {primary_duty} and related functions"
    else:
        duty_phrase = "responsible for key organizational functions"
    
    # Build supervisory sentence
    supervisory_sentence = ""
    if is_supervisor and num_supervised:
        supervisory_sentence = (
            f"\n\nAs a supervisor, this position oversees {num_supervised} employee"
            f"{'s' if num_supervised != 1 else ''}"
        )
        if percent_supervising:
            supervisory_sentence += f", dedicating approximately {percent_supervising}% of time to supervisory duties"
        supervisory_sentence += "."
    
    introduction = (
        f"The {position_id} serves as a key member of {org_phrase}. "
        f"This position reports to the {reports_to} and is {duty_phrase}."
        f"{supervisory_sentence}"
    )
    
    return introduction


def generate_background(interview_data: InterviewData) -> str:
    """
    Generate background section using procedural template.
    
    Provides organizational context and mission alignment based on
    interview data without requiring an LLM call.
    
    Args:
        interview_data: Collected interview responses
        
    Returns:
        Generated background text
    """
    position_title = interview_data.position_title.value or "this position"
    series = interview_data.series.value or ""
    grade = _extract_grade_display(interview_data.grade.value)
    org_hierarchy = interview_data.organization_hierarchy.value or interview_data.organization.value or []
    major_duties = interview_data.major_duties.value or []
    
    # Build organization description
    if org_hierarchy:
        if len(org_hierarchy) >= 3:
            top_org = org_hierarchy[0]
            mid_orgs = ", ".join(org_hierarchy[1:-1])
            bottom_org = org_hierarchy[-1]
            org_description = (
                f"The {bottom_org} is a component of {mid_orgs}, within {top_org}. "
            )
        elif len(org_hierarchy) == 2:
            org_description = (
                f"The {org_hierarchy[-1]} operates within {org_hierarchy[0]}. "
            )
        else:
            org_description = f"This position is located within {org_hierarchy[0]}. "
    else:
        org_description = ""
    
    # Build series context
    series_context = ""
    if series:
        series_context = _get_series_context(series)
    
    # Build position purpose — strip percentage breakdowns from duty text
    if major_duties:
        import re
        duty_list = major_duties[:3]
        cleaned_duties = [re.sub(r'\s*\d{1,3}\s*%\s*$', '', d).rstrip('. ') for d in duty_list]
        cleaned_duties = [d for d in cleaned_duties if d]  # drop empties
        if len(cleaned_duties) > 1:
            duties_text = ", ".join(d.lower() for d in cleaned_duties[:-1])
            duties_text += f", and {cleaned_duties[-1].lower()}"
        elif cleaned_duties:
            duties_text = cleaned_duties[0].lower()
        else:
            duties_text = "key technical and operational activities"
        purpose_statement = f"The {position_title} supports the organization's mission through {duties_text}. "
    else:
        purpose_statement = f"The {position_title} supports the organization's mission through key technical and operational activities. "
    
    # Build grade context
    grade_context = ""
    if grade:
        grade_num = _extract_grade_num(grade)
        if grade_num >= 13:
            grade_context = f" This is a senior-level position at the GS-{grade_num} grade level, requiring extensive expertise and independent judgment."
        elif grade_num >= 11:
            grade_context = f" This is a journey-level position at the GS-{grade_num} grade level."
        elif grade_num >= 7:
            grade_context = f" This is a developmental position at the GS-{grade_num} grade level."
    
    background = f"{org_description}{series_context}{purpose_statement}{grade_context}"
    
    return background


def _extract_grade_display(grade_value: str | None) -> str:
    """Extract grade number for display."""
    if not grade_value:
        return ""
    cleaned = str(grade_value).upper().replace("GS-", "").replace("GS", "").strip()
    try:
        return str(int(cleaned))
    except ValueError:
        return cleaned


def _extract_grade_num(grade_value: str | None) -> int:
    """Extract numeric grade from value."""
    if not grade_value:
        return 0
    cleaned = str(grade_value).upper().replace("GS-", "").replace("GS", "").strip()
    try:
        return int(cleaned)
    except ValueError:
        return 0


def _get_series_context(series: str) -> str:
    """Get contextual description for common series."""
    series_contexts = {
        "2210": "Positions in this series perform Information Technology management functions including applications software, operating systems, network services, and IT security. ",
        "0343": "Positions in this series perform management and program analysis work. ",
        "1102": "Positions in this series perform contracting and procurement work. ",
        "0201": "Positions in this series perform human resources management work. ",
        "0301": "Positions in this series perform miscellaneous administrative and program work. ",
        "0510": "Positions in this series perform accounting work. ",
        "0560": "Positions in this series perform budget analysis and administration work. ",
        "1550": "Positions in this series perform computer science work involving research and development. ",
        "1560": "Positions in this series perform data science work involving statistical analysis and machine learning. ",
    }
    return series_contexts.get(series, "")


# Mapping of section names to their procedural generators
PROCEDURAL_GENERATORS = {
    "introduction": generate_introduction,
    "background": generate_background,
}


def generate_procedural_content(
    section_name: str, 
    interview_data: InterviewData,
    **kwargs: Any
) -> str | None:
    """
    Generate content for a procedural section.
    
    Args:
        section_name: Name of the section to generate
        interview_data: Collected interview responses
        **kwargs: Additional context (unused by current generators)
        
    Returns:
        Generated content or None if section is not procedural
    """
    generator = PROCEDURAL_GENERATORS.get(section_name)
    if generator is None:
        logger.debug(f"No procedural generator for section: {section_name}")
        return None
    
    try:
        content = generator(interview_data)
        logger.info(f"Generated procedural content for {section_name} ({len(content)} chars)")
        return content
    except Exception as e:
        logger.error(f"Error generating procedural content for {section_name}: {e}")
        return None


def is_procedural_section(section_name: str) -> bool:
    """Check if a section has a procedural generator."""
    return section_name in PROCEDURAL_GENERATORS
