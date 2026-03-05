"""Unit tests for field validation utilities."""

import pytest

from src.validation import (
    parse_duties,
    parse_grade,
    parse_organization,
    validate_duty_percentages,
    validate_grade,
    validate_organization,
    validate_series,
)


class TestValidateSeries:
    """Tests for series code validation."""

    @pytest.mark.parametrize(
        "value",
        ["2210", "0343", "1550", "0801", "0301"],
    )
    def test_valid_series_codes(self, value: str):
        """Valid 4-digit series codes pass validation."""
        is_valid, error = validate_series(value)
        assert is_valid is True
        assert error is None

    @pytest.mark.parametrize(
        "value",
        ["343", "801", "1"],
    )
    def test_short_series_accepted(self, value: str):
        """Series codes without leading zeros are accepted."""
        is_valid, error = validate_series(value)
        assert is_valid is True

    @pytest.mark.parametrize(
        "value",
        ["", "abc", "12345", "2210x"],
    )
    def test_invalid_series_codes(self, value: str):
        """Invalid series codes fail validation."""
        is_valid, error = validate_series(value)
        # Non-digit strings and out-of-range values should fail
        if not value or not value.strip().replace("x", "").isdigit() or len(value) > 4:
            assert is_valid is False
            assert error is not None


class TestValidateGrade:
    """Tests for GS grade validation."""

    @pytest.mark.parametrize(
        "value",
        ["1", "5", "9", "10", "11", "12", "13", "14", "15", "GS-13", "GS13", "gs-14", "GS-9"],
    )
    def test_valid_grades(self, value: str):
        """Valid grades (1-15) pass validation."""
        is_valid, error = validate_grade(value)
        assert is_valid is True
        assert error is None

    @pytest.mark.parametrize(
        "value",
        ["", "0", "16", "17", "20", "abc", "GS-20"],
    )
    def test_invalid_grades(self, value: str):
        """Invalid grades (outside 1-15) fail validation."""
        is_valid, error = validate_grade(value)
        assert is_valid is False
        assert error is not None


class TestParseGrade:
    """Tests for grade parsing."""

    @pytest.mark.parametrize(
        "input_val,expected",
        [
            ("9", "GS-9"),
            ("GS-9", "GS-9"),
            ("13", "GS-13"),
            ("GS-13", "GS-13"),
            ("GS13", "GS-13"),
            ("gs-14", "GS-14"),
            ("Thirteen", "GS-13"),
            ("TWELVE", "GS-12"),
            ("grade 15", "GS-15"),
            ("Nine", "GS-9"),
            ("five", "GS-5"),
            ("1", "GS-1"),
        ],
    )
    def test_parse_various_formats(self, input_val: str, expected: str):
        """Parses various grade formats."""
        result = parse_grade(input_val)
        assert result == expected

    def test_parse_invalid_returns_none(self):
        """Returns None for invalid grades."""
        assert parse_grade("") is None
        assert parse_grade("20") is None
        assert parse_grade("abc") is None
        assert parse_grade("0") is None
        assert parse_grade("16") is None


class TestValidateOrganization:
    """Tests for organization validation."""

    def test_valid_organization(self):
        """Valid organization list passes."""
        is_valid, error = validate_organization(["VA", "VHA", "Office"])
        assert is_valid is True
        assert error is None

    def test_single_level_valid(self):
        """Single organization level is valid."""
        is_valid, error = validate_organization(["Department of Defense"])
        assert is_valid is True

    def test_empty_list_invalid(self):
        """Empty list fails validation."""
        is_valid, error = validate_organization([])
        assert is_valid is False
        assert error is not None

    def test_empty_strings_invalid(self):
        """List with only empty strings fails."""
        is_valid, error = validate_organization(["", "  "])
        assert is_valid is False


class TestParseOrganization:
    """Tests for organization parsing."""

    def test_comma_separated(self):
        """Parses comma-separated organization."""
        result = parse_organization("VA, VHA, Digital Health Office")
        assert result == ["VA", "VHA", "Digital Health Office"]

    def test_arrow_separated(self):
        """Parses arrow-separated organization."""
        result = parse_organization("VA > VHA > Digital Health")
        assert result == ["VA", "VHA", "Digital Health"]

    def test_slash_separated(self):
        """Parses slash-separated organization."""
        result = parse_organization("VA / VHA / Office")
        assert result == ["VA", "VHA", "Office"]

    def test_single_value(self):
        """Returns single value as list."""
        result = parse_organization("Department of Veterans Affairs")
        assert result == ["Department of Veterans Affairs"]

    def test_empty_string(self):
        """Returns empty list for empty string."""
        result = parse_organization("")
        assert result == []


class TestValidateDutyPercentages:
    """Tests for duty percentage validation."""

    def test_valid_100_percent(self):
        """Duties summing to 100% pass."""
        duties = {"Lead projects": 40, "Analyze data": 30, "Report": 30}
        is_valid, error = validate_duty_percentages(duties)
        assert is_valid is True

    def test_valid_with_tolerance(self):
        """Duties within tolerance (95-105%) pass."""
        duties = {"Lead projects": 50, "Analyze data": 48}  # 98%
        is_valid, error = validate_duty_percentages(duties)
        assert is_valid is True

    def test_string_percentages(self):
        """Handles string percentages."""
        duties = {"Lead projects": "40%", "Analyze data": "30%", "Report": "30%"}
        is_valid, error = validate_duty_percentages(duties)
        assert is_valid is True

    def test_empty_duties_invalid(self):
        """Empty duties dict fails."""
        is_valid, error = validate_duty_percentages({})
        assert is_valid is False

    def test_over_100_invalid(self):
        """Duties over 105% fail."""
        duties = {"Lead projects": 60, "Analyze data": 60}  # 120%
        is_valid, error = validate_duty_percentages(duties)
        assert is_valid is False

    def test_under_95_invalid(self):
        """Duties under 95% fail."""
        duties = {"Lead projects": 40, "Analyze data": 30}  # 70%
        is_valid, error = validate_duty_percentages(duties)
        assert is_valid is False


class TestParseDuties:
    """Tests for duty parsing."""

    def test_semicolon_separated(self):
        """Parses semicolon-separated duties."""
        result = parse_duties("Lead projects 40%; Analyze data 30%; Report 30%")
        assert result == {"Lead projects": 40, "Analyze data": 30, "Report": 30}

    def test_colon_format(self):
        """Parses colon format duties."""
        result = parse_duties("Lead projects: 40%; Analyze data: 30%")
        assert "Lead projects" in result
        assert result["Lead projects"] == 40

    def test_newline_separated(self):
        """Parses newline-separated duties."""
        result = parse_duties("Lead projects 40%\nAnalyze data 30%\nReport 30%")
        assert len(result) == 3
        assert result["Lead projects"] == 40

    def test_empty_string(self):
        """Returns empty dict for empty string."""
        result = parse_duties("")
        assert result == {}

    def test_no_percentages(self):
        """Handles duties without percentages."""
        result = parse_duties("Lead projects; Analyze data")
        assert "Lead projects" in result
        assert result["Lead projects"] == 0
