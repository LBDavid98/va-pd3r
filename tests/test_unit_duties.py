"""Unit tests for duty section models and series templates."""

import pytest

from src.config.series_templates import (
    SERIES_DUTY_TEMPLATES,
    get_available_templates,
    get_default_duty_weights,
    get_duty_template,
    has_duty_template,
    validate_duty_weights,
)
from src.models.duties import DutySection, SeriesDutyTemplate


class TestDutyModels:
    """Tests for duty Pydantic models."""

    def test_duty_section_creation(self):
        """Test creating a DutySection."""
        section = DutySection(
            title="Systems Analysis",
            percent_range=(20, 35),
            typical_weight=25,
            description="Analyze systems",
            example_tasks=["Task 1", "Task 2"],
        )
        assert section.title == "Systems Analysis"
        assert section.min_percent == 20
        assert section.max_percent == 35
        assert section.typical_weight == 25

    def test_duty_section_weight_validation(self):
        """Test DutySection weight validation."""
        section = DutySection(
            title="Test",
            percent_range=(20, 35),
            typical_weight=25,
            description="Test",
        )
        assert section.is_weight_valid(20) is True
        assert section.is_weight_valid(35) is True
        assert section.is_weight_valid(25) is True
        assert section.is_weight_valid(19) is False
        assert section.is_weight_valid(36) is False

    def test_series_duty_template_creation(self):
        """Test creating a SeriesDutyTemplate."""
        template = SeriesDutyTemplate(
            series="2210",
            grade=13,
            summary="Senior IT specialist",
            ncwf_codes=["651", "621"],
            duty_sections=[
                DutySection(
                    title="Section 1",
                    percent_range=(40, 60),
                    typical_weight=50,
                    description="Description 1",
                ),
                DutySection(
                    title="Section 2",
                    percent_range=(40, 60),
                    typical_weight=50,
                    description="Description 2",
                ),
            ],
        )
        assert template.series == "2210"
        assert template.grade == 13
        assert template.series_grade_key == "2210-13"
        assert len(template.duty_sections) == 2

    def test_series_duty_template_get_section(self):
        """Test getting a section by title."""
        template = SeriesDutyTemplate(
            series="2210",
            grade=13,
            summary="Test",
            duty_sections=[
                DutySection(
                    title="Test Section",
                    percent_range=(50, 50),
                    typical_weight=50,
                    description="Test",
                ),
            ],
        )
        section = template.get_section_by_title("Test Section")
        assert section is not None
        assert section.title == "Test Section"

        missing = template.get_section_by_title("Missing")
        assert missing is None

    def test_series_duty_template_validate_weights(self):
        """Test weight validation."""
        template = SeriesDutyTemplate(
            series="2210",
            grade=13,
            summary="Test",
            duty_sections=[
                DutySection(
                    title="Section A",
                    percent_range=(40, 60),
                    typical_weight=50,
                    description="A",
                ),
                DutySection(
                    title="Section B",
                    percent_range=(40, 60),
                    typical_weight=50,
                    description="B",
                ),
            ],
        )

        # Valid weights
        valid, errors = template.validate_weights({"Section A": 50, "Section B": 50})
        assert valid is True
        assert len(errors) == 0

        # Invalid - doesn't sum to 100
        invalid, errors = template.validate_weights({"Section A": 30, "Section B": 30})
        assert invalid is False
        assert any("sum to" in e for e in errors)

        # Invalid - out of range
        invalid, errors = template.validate_weights({"Section A": 90, "Section B": 10})
        assert invalid is False


class TestSeriesTemplatesConfig:
    """Tests for series template configuration loading."""

    def test_templates_loaded(self):
        """Test that templates are loaded from JSON."""
        assert len(SERIES_DUTY_TEMPLATES) > 0

    def test_get_available_templates(self):
        """Test getting available template keys."""
        available = get_available_templates()
        assert len(available) > 0
        assert "2210-13" in available or "2210-14" in available

    def test_has_duty_template(self):
        """Test checking for template existence."""
        # 2210 should have templates
        assert has_duty_template("2210", 13) or has_duty_template("2210", 14)

        # Random series shouldn't
        assert has_duty_template("9999", 13) is False

    def test_get_duty_template(self):
        """Test getting a specific template."""
        # Get a template that exists
        template = get_duty_template("2210", 13)
        if template:
            assert template.series == "2210"
            assert template.grade == 13
            assert len(template.duty_sections) > 0

    def test_get_duty_template_missing(self):
        """Test getting a non-existent template."""
        template = get_duty_template("9999", 99)
        assert template is None

    def test_validate_duty_weights_no_template(self):
        """Test validation when no template exists."""
        # Should return True (no validation needed)
        valid, errors = validate_duty_weights("9999", 99, {})
        assert valid is True
        assert len(errors) == 0

    def test_get_default_duty_weights(self):
        """Test getting default weights."""
        weights = get_default_duty_weights("2210", 13)
        if weights:
            assert len(weights) > 0
            # Check that all values are reasonable percentages
            for title, weight in weights.items():
                assert 0 <= weight <= 100

        # Missing template returns None
        missing = get_default_duty_weights("9999", 99)
        assert missing is None


class TestDutyTemplate2210:
    """Specific tests for GS-2210 templates."""

    @pytest.fixture
    def gs2210_13(self):
        """Get GS-2210-13 template."""
        return get_duty_template("2210", 13)

    def test_gs2210_13_exists(self, gs2210_13):
        """Test that GS-2210-13 template exists."""
        assert gs2210_13 is not None

    def test_gs2210_13_has_sections(self, gs2210_13):
        """Test that GS-2210-13 has duty sections."""
        if gs2210_13:
            assert len(gs2210_13.duty_sections) >= 3

    def test_gs2210_13_section_weights_valid(self, gs2210_13):
        """Test that default weights are valid."""
        if gs2210_13:
            weights = gs2210_13.get_default_weights()
            # Default weights should be within ranges
            for section in gs2210_13.duty_sections:
                weight = weights.get(section.title, 0)
                assert section.is_weight_valid(weight), f"{section.title} weight {weight} not in range"
