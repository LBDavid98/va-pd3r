"""Series-specific duty template configuration.

Loads and provides access to duty templates for specific series/grade
combinations. Currently supports GS-2210 (IT Management) series.
"""

import json
from pathlib import Path

from src.models.duties import DutySection, SeriesDutyTemplate

# Path to business rules JSON files
BUSINESS_RULES_DIR = Path(__file__).parent.parent.parent / "docs" / "business_rules"

# Load series duty templates from JSON
_templates_path = BUSINESS_RULES_DIR / "gs2210_major_duties_templates.json"
with open(_templates_path) as f:
    _raw_templates = json.load(f)

# Parse templates into models
SERIES_DUTY_TEMPLATES: dict[str, SeriesDutyTemplate] = {}

_series = _raw_templates.get("series", "2210")
_gs_templates = _raw_templates.get("gs_templates", {})

for grade_str, template_data in _gs_templates.items():
    grade = int(grade_str)

    # Parse duty sections
    duty_sections = []
    for section_data in template_data.get("duty_sections", []):
        duty_sections.append(
            DutySection(
                title=section_data["title"],
                percent_range=tuple(section_data["percent_range"]),
                typical_weight=section_data["typical_weight"],
                description=section_data["description"],
                example_tasks=section_data.get("example_tasks", []),
            )
        )

    # Build template
    template = SeriesDutyTemplate(
        series=_series,
        grade=grade,
        summary=template_data.get("summary", ""),
        ncwf_codes=template_data.get("ncwf_codes", []),
        duty_sections=duty_sections,
    )

    # Store with series-grade key
    SERIES_DUTY_TEMPLATES[template.series_grade_key] = template


def get_duty_template(series: str, grade: int) -> SeriesDutyTemplate | None:
    """
    Get duty template for a series/grade combination.

    Args:
        series: OPM series code (e.g., '2210')
        grade: GS grade number (e.g., 13)

    Returns:
        SeriesDutyTemplate or None if no template exists for this combination
    """
    key = f"{series}-{grade}"
    return SERIES_DUTY_TEMPLATES.get(key)


def has_duty_template(series: str, grade: int) -> bool:
    """Check if a duty template exists for this series/grade."""
    key = f"{series}-{grade}"
    return key in SERIES_DUTY_TEMPLATES


def get_available_templates() -> list[str]:
    """Return list of available series-grade keys."""
    return list(SERIES_DUTY_TEMPLATES.keys())


def validate_duty_weights(
    series: str, grade: int, weights: dict[str, int]
) -> tuple[bool, list[str]]:
    """
    Validate duty section weights against the template.

    Args:
        series: OPM series code
        grade: GS grade number
        weights: Dict mapping section title to percent weight

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    template = get_duty_template(series, grade)
    if template is None:
        return True, []  # No template = no validation required

    return template.validate_weights(weights)


def get_default_duty_weights(series: str, grade: int) -> dict[str, int] | None:
    """
    Get default duty weights for a series/grade.

    Args:
        series: OPM series code
        grade: GS grade number

    Returns:
        Dict of section title to typical weight, or None if no template
    """
    template = get_duty_template(series, grade)
    if template is None:
        return None

    return template.get_default_weights()
