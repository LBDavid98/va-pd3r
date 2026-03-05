"""Duty section models for series-specific position descriptions.

For certain series (like 2210 IT Management), mandatory duty sections must
appear in major duties with weights within specified percent ranges.
"""

from pydantic import BaseModel, Field


class DutySection(BaseModel):
    """
    A duty section within a position description's major duties.

    Each section has a title, percent weight range, and description
    of the duties performed.
    """

    title: str = Field(..., description="Section title (e.g., 'Systems Analysis and Integration')")
    percent_range: tuple[int, int] = Field(
        ..., description="Min and max percent weight for this section (e.g., (20, 35))"
    )
    typical_weight: int = Field(
        ..., description="Typical/recommended weight percentage"
    )
    description: str = Field(
        ..., description="Description of duties in this section"
    )
    example_tasks: list[str] = Field(
        default_factory=list,
        description="Example tasks that might appear in this section",
    )

    @property
    def min_percent(self) -> int:
        """Minimum allowed percentage."""
        return self.percent_range[0]

    @property
    def max_percent(self) -> int:
        """Maximum allowed percentage."""
        return self.percent_range[1]

    def is_weight_valid(self, weight: int) -> bool:
        """Check if a weight is within the allowed range."""
        return self.min_percent <= weight <= self.max_percent


class SeriesDutyTemplate(BaseModel):
    """
    Series-specific duty template for a grade level.

    Contains the mandatory duty sections that must appear in a position
    description for this series/grade combination.
    """

    series: str = Field(..., description="OPM series code (e.g., '2210')")
    grade: int = Field(..., description="GS grade number")
    summary: str = Field(..., description="Brief description of the role at this level")
    ncwf_codes: list[str] = Field(
        default_factory=list,
        description="NICE Cybersecurity Workforce Framework codes",
    )
    duty_sections: list[DutySection] = Field(
        default_factory=list,
        description="Mandatory duty sections for this series/grade",
    )

    @property
    def series_grade_key(self) -> str:
        """Return key for lookup (e.g., '2210-13')."""
        return f"{self.series}-{self.grade}"

    def get_section_by_title(self, title: str) -> DutySection | None:
        """Find a duty section by its title."""
        for section in self.duty_sections:
            if section.title.lower() == title.lower():
                return section
        return None

    def validate_weights(self, weights: dict[str, int]) -> tuple[bool, list[str]]:
        """
        Validate that section weights are correct.

        Args:
            weights: Dict mapping section title to percent weight

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []

        # Check total sums to 100
        total = sum(weights.values())
        if total != 100:
            errors.append(f"Section weights sum to {total}%, must equal 100%")

        # Check each section is within its allowed range
        for section in self.duty_sections:
            weight = weights.get(section.title, 0)
            if weight == 0:
                errors.append(f"Missing weight for required section: {section.title}")
            elif not section.is_weight_valid(weight):
                errors.append(
                    f"Section '{section.title}' has weight {weight}%, "
                    f"must be between {section.min_percent}% and {section.max_percent}%"
                )

        return len(errors) == 0, errors

    def get_default_weights(self) -> dict[str, int]:
        """
        Get default weights for all sections using typical_weight.

        Note: May not sum to exactly 100; use as starting point.
        """
        return {section.title: section.typical_weight for section in self.duty_sections}
