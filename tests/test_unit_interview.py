"""Unit tests for interview models."""

import pytest

from src.models.interview import InterviewData, InterviewElement


class TestInterviewElement:
    """Tests for InterviewElement generic model."""

    def test_default_state(self):
        """New element has no value and is not set."""
        element = InterviewElement[str]()

        assert element.value is None
        assert element.raw_input is None
        assert element.needs_confirmation is False
        assert element.confirmed is False
        assert element.is_set is False

    def test_set_value_basic(self):
        """set_value stores value and marks as set."""
        element = InterviewElement[str]()

        element.set_value("Test Value")

        assert element.value == "Test Value"
        assert element.is_set is True
        assert element.raw_input is None
        assert element.needs_confirmation is False

    def test_set_value_with_metadata(self):
        """set_value stores raw_input and needs_confirmation."""
        element = InterviewElement[str]()

        element.set_value(
            value="GS-12",
            raw_input="I think it's a GS-12 position",
            needs_confirmation=True,
        )

        assert element.value == "GS-12"
        assert element.raw_input == "I think it's a GS-12 position"
        assert element.needs_confirmation is True
        assert element.confirmed is False

    def test_set_value_resets_confirmed(self):
        """Setting a new value resets confirmed flag."""
        element = InterviewElement[str]()
        element.set_value("Original")
        element.confirm()

        assert element.confirmed is True

        element.set_value("New Value")

        assert element.confirmed is False

    def test_confirm(self):
        """confirm() sets confirmed and clears needs_confirmation."""
        element = InterviewElement[str]()
        element.set_value("Value", needs_confirmation=True)

        assert element.needs_confirmation is True
        assert element.confirmed is False

        element.confirm()

        assert element.confirmed is True
        assert element.needs_confirmation is False

    def test_clear(self):
        """clear() resets all fields to default."""
        element = InterviewElement[str]()
        element.set_value("Value", raw_input="input", needs_confirmation=True)
        element.confirm()

        element.clear()

        assert element.value is None
        assert element.raw_input is None
        assert element.needs_confirmation is False
        assert element.confirmed is False
        assert element.is_set is False

    def test_generic_with_list(self):
        """InterviewElement works with list types."""
        element = InterviewElement[list[str]]()

        element.set_value(["Duty 1", "Duty 2", "Duty 3"])

        assert element.value == ["Duty 1", "Duty 2", "Duty 3"]
        assert element.is_set is True

    def test_generic_with_bool(self):
        """InterviewElement works with bool types."""
        element = InterviewElement[bool]()

        element.set_value(True)

        assert element.value is True
        assert element.is_set is True

    def test_generic_with_int(self):
        """InterviewElement works with int types."""
        element = InterviewElement[int]()

        element.set_value(5)

        assert element.value == 5
        assert element.is_set is True


class TestInterviewData:
    """Tests for InterviewData model."""

    def test_default_state(self):
        """New InterviewData has all fields unset."""
        data = InterviewData()

        assert data.position_title.is_set is False
        assert data.series.is_set is False
        assert data.grade.is_set is False
        assert data.major_duties.is_set is False

    def test_iteration(self):
        """Can iterate over field names and elements."""
        data = InterviewData()
        data.position_title.set_value("IT Specialist")

        fields = list(data)

        assert len(fields) > 0
        assert ("position_title", data.position_title) in fields

    def test_get_set_fields(self):
        """get_set_fields returns only fields with values."""
        data = InterviewData()
        data.position_title.set_value("IT Specialist")
        data.series.set_value("2210")

        set_fields = data.get_set_fields()

        assert "position_title" in set_fields
        assert "series" in set_fields
        assert "grade" not in set_fields
        assert len(set_fields) == 2

    def test_get_fields_needing_confirmation(self):
        """get_fields_needing_confirmation returns uncertain fields."""
        data = InterviewData()
        data.position_title.set_value("IT Specialist")
        data.series.set_value("2210", needs_confirmation=True)
        data.grade.set_value("GS-13", needs_confirmation=True)
        data.grade.confirm()  # This one is now confirmed

        needing_confirmation = data.get_fields_needing_confirmation()

        assert "series" in needing_confirmation
        assert "grade" not in needing_confirmation  # Already confirmed
        assert "position_title" not in needing_confirmation  # Never needed confirmation

    def test_get_unset_required_fields(self):
        """get_unset_required_fields filters by required list."""
        data = InterviewData()
        data.position_title.set_value("IT Specialist")
        data.series.set_value("2210")

        required = ["position_title", "series", "grade", "major_duties"]
        unset = data.get_unset_required_fields(required)

        assert "grade" in unset
        assert "major_duties" in unset
        assert "position_title" not in unset
        assert "series" not in unset

    def test_to_summary_dict(self):
        """to_summary_dict returns simple dict of values."""
        data = InterviewData()
        data.position_title.set_value("IT Specialist")
        data.series.set_value("2210")
        data.major_duties.set_value(["Design systems", "Review code"])

        summary = data.to_summary_dict()

        assert summary["position_title"] == "IT Specialist"
        assert summary["series"] == "2210"
        assert summary["major_duties"] == ["Design systems", "Review code"]
        assert "grade" not in summary  # Not set

    def test_serialization_roundtrip(self):
        """InterviewData can be serialized and restored."""
        data = InterviewData()
        data.position_title.set_value("IT Specialist", raw_input="I need an IT Specialist")
        data.series.set_value("2210", needs_confirmation=True)
        data.is_supervisor.set_value(True)
        data.is_supervisor.confirm()

        # Serialize
        serialized = data.model_dump()

        # Deserialize
        restored = InterviewData.model_validate(serialized)

        assert restored.position_title.value == "IT Specialist"
        assert restored.position_title.raw_input == "I need an IT Specialist"
        assert restored.series.needs_confirmation is True
        assert restored.is_supervisor.confirmed is True
