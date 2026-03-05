"""Requirements models for draft generation.

DraftRequirements encapsulates all the constraints and requirements
that must be met when generating a position description, including:
- FES factor "does" statements that must appear
- Series-specific duty section requirements
- Interview-derived constraints
"""

from typing import Literal

from pydantic import BaseModel, Field

from src.models.duties import SeriesDutyTemplate
from src.models.fes import FESEvaluation


class DraftRequirement(BaseModel):
    """
    A single requirement that must be met in the draft.

    IMPORTANT: All requirements are evaluated by LLM, NOT by keyword matching.
    The `target_content` field provides context/examples for the LLM to evaluate,
    NOT a list of strings to grep for. See qa_review.jinja for evaluation logic.

    Requirements can be:
    - Inclusion (default): Content concepts SHOULD appear (e.g., FES "does" statements)
    - Exclusion: Content concepts SHOULD NOT appear (e.g., FES "does_not" statements)
    
    Requirements can also be:
    - Critical (default): Must pass for QA to succeed
    - Advisory: Should pass, but draft can proceed without
    """

    id: str = Field(..., description="Unique identifier for the requirement")
    description: str = Field(..., description="Human-readable description")
    element_name: str = Field(
        ...,
        description="Which draft element this applies to (e.g., 'factor_1', 'major_duties')",
    )
    check_type: Literal["keyword", "semantic", "weight", "structure"] = Field(
        ..., 
        description="Hint for LLM on evaluation approach: "
        "'keyword' = look for specific terms, "
        "'semantic' = evaluate meaning/concept coverage, "
        "'weight' = check percentage allocations, "
        "'structure' = verify structural elements present"
    )
    # NOTE: This field was renamed from 'keywords' to clarify it's LLM context, not grep patterns
    target_content: list[str] = Field(
        default_factory=list,
        description="Content, phrases, or concepts for LLM to evaluate against. "
        "The LLM uses these as reference for semantic evaluation, NOT exact string matching.",
        alias="keywords",  # Backward compatibility with existing serialized data
    )
    is_exclusion: bool = Field(
        default=False,
        description="If True, LLM checks that target_content concepts are ABSENT. "
        "If False (default), LLM checks that concepts are PRESENT.",
    )
    is_critical: bool = Field(
        default=True, description="Whether this requirement is mandatory for QA pass"
    )
    source: str = Field(
        default="", description="Where this requirement came from (e.g., 'FES Factor 1')"
    )

    # Additional context for semantic/weight checks
    min_weight: int | None = Field(
        default=None, description="Minimum percentage weight (for duty sections)"
    )
    max_weight: int | None = Field(
        default=None, description="Maximum percentage weight (for duty sections)"
    )
    
    model_config = {"populate_by_name": True}  # Allow both 'keywords' and 'target_content'


class DraftRequirements(BaseModel):
    """
    Collection of all requirements for a position description draft.

    Aggregates requirements from:
    - FES evaluation (does statements)
    - Series-specific duty templates
    - Interview data constraints
    """

    requirements: list[DraftRequirement] = Field(
        default_factory=list, description="All requirements to check"
    )

    # Source data
    fes_evaluation: FESEvaluation | None = Field(
        default=None, description="FES evaluation used to generate requirements"
    )
    duty_template: SeriesDutyTemplate | None = Field(
        default=None, description="Series duty template if applicable"
    )

    # Metadata
    series: str | None = Field(default=None, description="Position series code")
    grade: int | None = Field(default=None, description="Target GS grade")
    is_supervisor: bool = Field(
        default=False, description="Whether this is a supervisory position"
    )

    def get_requirements_for_element(self, element_name: str) -> list[DraftRequirement]:
        """
        Get all requirements that apply to a specific draft element.

        Args:
            element_name: Name of the element (e.g., 'factor_1', 'major_duties')

        Returns:
            List of requirements for that element
        """
        return [r for r in self.requirements if r.element_name == element_name]

    def get_critical_requirements(self) -> list[DraftRequirement]:
        """Get all critical (mandatory) requirements."""
        return [r for r in self.requirements if r.is_critical]

    def get_advisory_requirements(self) -> list[DraftRequirement]:
        """Get all advisory (non-critical) requirements."""
        return [r for r in self.requirements if not r.is_critical]

    def get_fes_requirements(self) -> list[DraftRequirement]:
        """Get requirements derived from FES evaluation."""
        return [r for r in self.requirements if r.source.startswith("FES")]

    def get_duty_requirements(self) -> list[DraftRequirement]:
        """Get requirements derived from duty template."""
        return [r for r in self.requirements if r.source.startswith("Duty")]

    @property
    def has_duty_template(self) -> bool:
        """Check if there's a series-specific duty template."""
        return self.duty_template is not None

    @property
    def total_count(self) -> int:
        """Total number of requirements."""
        return len(self.requirements)

    @property
    def critical_count(self) -> int:
        """Count of critical requirements."""
        return len(self.get_critical_requirements())

    def add_requirement(self, requirement: DraftRequirement) -> None:
        """Add a requirement to the collection."""
        self.requirements.append(requirement)

    def to_summary(self) -> str:
        """Generate a human-readable summary of requirements."""
        lines = [
            f"Draft Requirements for GS-{self.grade} {self.series or 'position'}",
            f"  Total requirements: {self.total_count}",
            f"  Critical: {self.critical_count}",
            f"  Advisory: {len(self.get_advisory_requirements())}",
        ]

        if self.fes_evaluation:
            lines.append(f"  FES factors: {len(self.fes_evaluation.all_factors)}")

        if self.duty_template:
            lines.append(
                f"  Duty sections: {len(self.duty_template.duty_sections)}"
            )

        return "\n".join(lines)
