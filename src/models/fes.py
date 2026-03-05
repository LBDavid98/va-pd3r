"""FES (Federal Evaluation System) models for grade evaluation.

The FES uses 9 factors to determine GS grade levels:
- Primary Factors (1-5): Separately evaluated sections
- Other Significant Factors (6-9): Combined into single section at end of PD

Each factor has defined levels with specific "DOES" statements that MUST appear
in the position description.
"""

from typing import Union

from pydantic import BaseModel, Field


class FESFactorLevel(BaseModel):
    """
    A specific level within an FES factor.

    Contains the "does" statements that describe what an employee
    at this level actually does. These MUST appear in the PD.
    """

    factor_num: Union[int, str] = Field(
        ..., description="Factor number (1-9, or 'a'-'d' for factor 7)"
    )
    factor_name: str = Field(..., description="Human-readable factor name")
    level: Union[int, str] = Field(
        ..., description="Level within factor (e.g., 3 for '1-3', 'b' for factor 7)"
    )
    level_code: str = Field(
        ..., description="Full level code as it appears in reference (e.g., '1-3', '2-4', 'b')"
    )
    points: int = Field(..., description="Point value for this level")
    does: list[str] = Field(
        default_factory=list,
        description="List of 'does' statements for this level (expanded, no markers)",
    )

    @property
    def display_level(self) -> str:
        """Return display-friendly level string."""
        return f"Factor {self.factor_num} Level {self.level_code}"


class FESEvaluation(BaseModel):
    """
    Complete FES evaluation for a position.

    Contains factor levels for all 9 factors based on the target grade.
    Primary factors (1-5) are separately evaluated sections in the PD.
    Other significant factors (6-9) are combined into a single section.
    """

    grade: str = Field(..., description="Target GS grade (e.g., 'GS-13')")
    grade_num: int = Field(..., description="Numeric grade for calculations")

    # Primary factors (1-5) - each gets its own section
    factor_1_knowledge: FESFactorLevel | None = Field(
        default=None, description="Factor 1: Knowledge Required by the Position"
    )
    factor_2_supervisory_controls: FESFactorLevel | None = Field(
        default=None, description="Factor 2: Supervisory Controls"
    )
    factor_3_guidelines: FESFactorLevel | None = Field(
        default=None, description="Factor 3: Guidelines"
    )
    factor_4_complexity: FESFactorLevel | None = Field(
        default=None, description="Factor 4: Complexity"
    )
    factor_5_scope_and_effect: FESFactorLevel | None = Field(
        default=None, description="Factor 5: Scope and Effect"
    )

    # Other significant factors (6-9) - combined into one section
    factor_6_personal_contacts: FESFactorLevel | None = Field(
        default=None, description="Factor 6: Personal Contacts"
    )
    factor_7_purpose_of_contacts: FESFactorLevel | None = Field(
        default=None, description="Factor 7: Purpose of Contacts"
    )
    factor_8_physical_demands: FESFactorLevel | None = Field(
        default=None, description="Factor 8: Physical Demands"
    )
    factor_9_work_environment: FESFactorLevel | None = Field(
        default=None, description="Factor 9: Work Environment"
    )

    total_points: int = Field(default=0, description="Sum of all factor points")

    @property
    def primary_factors(self) -> list[FESFactorLevel]:
        """Return list of primary factors (1-5) that have values."""
        factors = [
            self.factor_1_knowledge,
            self.factor_2_supervisory_controls,
            self.factor_3_guidelines,
            self.factor_4_complexity,
            self.factor_5_scope_and_effect,
        ]
        return [f for f in factors if f is not None]

    @property
    def other_significant_factors(self) -> list[FESFactorLevel]:
        """Return list of other significant factors (6-9) that have values."""
        factors = [
            self.factor_6_personal_contacts,
            self.factor_7_purpose_of_contacts,
            self.factor_8_physical_demands,
            self.factor_9_work_environment,
        ]
        return [f for f in factors if f is not None]

    @property
    def all_factors(self) -> list[FESFactorLevel]:
        """Return all factors that have values."""
        return self.primary_factors + self.other_significant_factors

    def get_factor(self, factor_num: int) -> FESFactorLevel | None:
        """Get a specific factor by number."""
        factor_map = {
            1: self.factor_1_knowledge,
            2: self.factor_2_supervisory_controls,
            3: self.factor_3_guidelines,
            4: self.factor_4_complexity,
            5: self.factor_5_scope_and_effect,
            6: self.factor_6_personal_contacts,
            7: self.factor_7_purpose_of_contacts,
            8: self.factor_8_physical_demands,
            9: self.factor_9_work_environment,
        }
        return factor_map.get(factor_num)

    def get_all_does_statements(self) -> dict[int, list[str]]:
        """Return all 'does' statements grouped by factor number."""
        result = {}
        for factor in self.all_factors:
            factor_num = int(factor.factor_num) if isinstance(factor.factor_num, str) else factor.factor_num
            result[factor_num] = factor.does
        return result


class GradeCutoff(BaseModel):
    """
    Grade cutoff information for FES point ranges.

    Maps GS grades to their point ranges and typical factor levels.
    """

    grade: int = Field(..., description="GS grade number (e.g., 13)")
    min_points: int = Field(..., description="Minimum total points for this grade")
    max_points: int | None = Field(
        default=None, description="Maximum total points for this grade (None for GS-15)"
    )

    # Factor ranges for this grade - keyed by factor number
    # Each contains min/max with score and points
    factors: dict[str, dict] = Field(
        default_factory=dict,
        description="Factor configurations for this grade level",
    )

    def get_factor_level(self, factor_num: int, use_max: bool = False) -> tuple[Union[int, str], int]:
        """
        Get the score and points for a factor at this grade.

        Args:
            factor_num: Factor number (1-9)
            use_max: If True, return max level; otherwise return min

        Returns:
            Tuple of (score/level, points)
        """
        factor_key = str(factor_num)
        if factor_key not in self.factors:
            return (0, 0)

        factor_data = self.factors[factor_key]
        key = "max" if use_max else "min"
        return (factor_data[key]["score"], factor_data[key]["points"])

    @property
    def display_range(self) -> str:
        """Return display-friendly point range string."""
        if self.max_points is None:
            return f"{self.min_points}+"
        return f"{self.min_points}-{self.max_points}"
