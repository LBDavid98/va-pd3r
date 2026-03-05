"""Unit tests for Pydantic models."""

import pytest
from pydantic import ValidationError

from src.models.position import PositionDescription


def test_position_description_valid():
    """Test valid position description creation."""
    pd = PositionDescription(
        title="IT Specialist",
        series="2210",
        grade="GS-13",
        duties=["Develop software", "Review code"],
        qualifications=["5 years experience"],
    )
    assert pd.title == "IT Specialist"
    assert pd.series == "2210"
    assert pd.grade == "GS-13"


def test_position_description_strips_whitespace():
    """Test that title whitespace is stripped."""
    pd = PositionDescription(
        title="  IT Specialist  ",
        series="2210",
        grade="GS-13",
    )
    assert pd.title == "IT Specialist"


def test_position_description_invalid_series():
    """Test that invalid series raises error."""
    with pytest.raises(ValidationError):
        PositionDescription(
            title="IT Specialist",
            series="22",  # Must be 4 digits
            grade="GS-13",
        )


def test_position_description_invalid_grade():
    """Test that invalid grade raises error."""
    with pytest.raises(ValidationError):
        PositionDescription(
            title="IT Specialist",
            series="2210",
            grade="13",  # Must be GS-XX format
        )


def test_position_description_filters_empty_duties():
    """Test that empty duties are filtered out."""
    pd = PositionDescription(
        title="IT Specialist",
        series="2210",
        grade="GS-13",
        duties=["Develop software", "", "  ", "Review code"],
    )
    assert pd.duties == ["Develop software", "Review code"]
