"""Position Description model - source of truth."""

from pydantic import BaseModel, Field, field_validator


class PositionDescription(BaseModel):
    """Federal position description model."""

    title: str = Field(..., min_length=1, description="Position title")
    series: str = Field(..., pattern=r"^\d{4}$", description="4-digit OPM series code")
    grade: str = Field(..., pattern=r"^GS-\d{1,2}$", description="GS grade level")
    duties: list[str] = Field(default_factory=list, description="Major duties")
    qualifications: list[str] = Field(default_factory=list, description="Required qualifications")
    summary: str = Field(default="", description="Position summary")

    @field_validator("title", "summary", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """Strip whitespace from string fields."""
        return v.strip() if isinstance(v, str) else v

    @field_validator("duties", "qualifications", mode="before")
    @classmethod
    def filter_empty(cls, v: list) -> list:
        """Remove empty strings from lists."""
        if isinstance(v, list):
            return [item.strip() for item in v if item and item.strip()]
        return v
