"""Interview models for collecting position description data."""

from typing import Any, Generic, Iterator, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class InterviewElement(BaseModel, Generic[T]):
    """
    Interview element with value and lightweight metadata.

    Generic container for interview data that tracks:
    - The captured value
    - Original user input (for context)
    - Confirmation status for uncertain extractions
    """

    value: Optional[T] = None
    raw_input: Optional[str] = None  # Original text that yielded this value
    needs_confirmation: bool = False  # Flag for uncertain extractions
    confirmed: bool = False  # User explicitly confirmed

    @property
    def is_set(self) -> bool:
        """Check if value has been captured."""
        return self.value is not None

    def set_value(
        self,
        value: T,
        raw_input: Optional[str] = None,
        needs_confirmation: bool = False,
    ) -> None:
        """
        Set value with optional metadata.

        Args:
            value: The parsed/structured value to store
            raw_input: Original user text this was extracted from
            needs_confirmation: Whether this extraction is uncertain
        """
        self.value = value
        self.raw_input = raw_input
        self.needs_confirmation = needs_confirmation
        self.confirmed = False  # Reset on new value

    def confirm(self) -> None:
        """Mark this value as confirmed by user."""
        self.confirmed = True
        self.needs_confirmation = False

    def clear(self) -> None:
        """Clear all value and metadata."""
        self.value = None
        self.raw_input = None
        self.needs_confirmation = False
        self.confirmed = False


class InterviewData(BaseModel):
    """
    Collected interview responses with per-element metadata.

    Contains all fields needed to generate a federal position description.
    Each field is wrapped in InterviewElement for metadata tracking.
    """

    # Core position information
    position_title: InterviewElement[str] = Field(default_factory=InterviewElement)
    organization: InterviewElement[list[str]] = Field(
        default_factory=InterviewElement
    )  # Legacy field - use organization_hierarchy
    organization_hierarchy: InterviewElement[list[str]] = Field(
        default_factory=InterviewElement
    )  # Hierarchical org path
    series: InterviewElement[str] = Field(
        default_factory=InterviewElement
    )  # 4-digit OPM code
    grade: InterviewElement[str] = Field(
        default_factory=InterviewElement
    )  # GS-XX format

    # Supervisory information
    is_supervisor: InterviewElement[bool] = Field(
        default_factory=InterviewElement
    )  # Whether position supervises others
    num_supervised: InterviewElement[int] = Field(
        default_factory=InterviewElement
    )  # Conditional on is_supervisor
    percent_supervising: InterviewElement[int] = Field(
        default_factory=InterviewElement
    )  # Conditional on is_supervisor
    supervised_employees: InterviewElement[Any] = Field(
        default_factory=InterviewElement
    )  # Employee data — LLM may return str, list, or dict

    # Supervisory factors (conditional on is_supervisor=True)
    # LLM may return str, int, or structured dict — use Any to accept all formats
    f1_program_scope: InterviewElement[Any] = Field(
        default_factory=InterviewElement
    )  # Scope and effect of the program
    f2_organizational_setting: InterviewElement[Any] = Field(
        default_factory=InterviewElement
    )  # Org level/complexity
    f3_supervisory_authorities: InterviewElement[Any] = Field(
        default_factory=InterviewElement
    )  # Authorities exercised
    f4_key_contacts: InterviewElement[Any] = Field(
        default_factory=InterviewElement
    )  # Contact level/importance
    f5_subordinate_details: InterviewElement[str] = Field(
        default_factory=InterviewElement
    )  # Description of subordinate work and mission
    f6_special_conditions: InterviewElement[str] = Field(
        default_factory=InterviewElement
    )  # Special conditions affecting supervision

    # Organizational context (settings-provided, not interview-collected)
    mission_text: InterviewElement[str] = Field(default_factory=InterviewElement)

    # Reporting structure
    reports_to: InterviewElement[str] = Field(default_factory=InterviewElement)

    # Position content
    daily_activities: InterviewElement[list[str]] = Field(
        default_factory=InterviewElement
    )  # Day-to-day tasks
    major_duties: InterviewElement[list[str]] = Field(default_factory=InterviewElement)
    qualifications: InterviewElement[list[str]] = Field(
        default_factory=InterviewElement
    )
    work_environment: InterviewElement[str] = Field(default_factory=InterviewElement)
    physical_demands: InterviewElement[str] = Field(default_factory=InterviewElement)

    # Travel and location
    travel_required: InterviewElement[bool] = Field(default_factory=InterviewElement)
    travel_percentage: InterviewElement[int] = Field(default_factory=InterviewElement)

    def __iter__(self) -> Iterator[tuple[str, InterviewElement]]:
        """Iterate over field name and InterviewElement pairs."""
        for field_name in self.__class__.model_fields:
            yield field_name, getattr(self, field_name)

    def get_fields_needing_confirmation(self) -> list[str]:
        """
        Return list of field names that need user confirmation.

        These are fields where:
        - A value has been set
        - The extraction was flagged as uncertain
        - User has not yet confirmed
        """
        return [
            field_name
            for field_name, field_value in self
            if isinstance(field_value, InterviewElement)
            and field_value.is_set
            and field_value.needs_confirmation
            and not field_value.confirmed
        ]

    def get_set_fields(self) -> list[str]:
        """Return list of field names that have values set."""
        return [
            field_name
            for field_name, field_value in self
            if isinstance(field_value, InterviewElement) and field_value.is_set
        ]

    def get_unset_required_fields(self, required_fields: list[str]) -> list[str]:
        """
        Return required fields that don't have values set.

        Args:
            required_fields: List of field names that are required

        Returns:
            List of required field names without values
        """
        return [
            field_name
            for field_name in required_fields
            if hasattr(self, field_name)
            and not getattr(self, field_name).is_set
        ]

    def to_summary_dict(self) -> dict[str, any]:
        """
        Return a simplified dict with just field names and values.

        Useful for display or serialization without metadata.
        """
        return {
            field_name: field_value.value
            for field_name, field_value in self
            if isinstance(field_value, InterviewElement) and field_value.is_set
        }
