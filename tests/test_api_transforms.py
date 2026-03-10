"""Tests for src/api/transforms.py — QA review transformation."""

import pytest
from src.api.transforms import qa_review_to_summary


class TestQaReviewToSummary:
    """Test the single-source-of-truth QA transformation."""

    def test_none_returns_none(self):
        assert qa_review_to_summary(None) is None

    def test_dict_input_basic(self):
        raw = {
            "passes": True,
            "overall_feedback": "Looks good",
            "check_results": [
                {
                    "requirement_id": "req-1",
                    "passed": True,
                    "explanation": "Met",
                    "severity": "critical",
                    "suggestion": None,
                }
            ],
            "passed_count": 1,
            "failed_count": 0,
        }
        result = qa_review_to_summary(raw)
        assert result["passes"] is True
        assert result["overall_feedback"] == "Looks good"
        assert len(result["checks"]) == 1
        assert result["checks"][0]["requirement_id"] == "req-1"
        assert result["checks"][0]["passed"] is True
        assert result["passed_count"] == 1
        assert result["failed_count"] == 0

    def test_dict_input_uses_checks_key_fallback(self):
        """Streaming events may use 'checks' instead of 'check_results'."""
        raw = {
            "passes": False,
            "overall_feedback": "Needs work",
            "checks": [
                {
                    "requirement_id": "req-2",
                    "passed": False,
                    "explanation": "Missing content",
                    "severity": "warning",
                    "suggestion": "Add more detail",
                }
            ],
            "passed_count": 0,
            "failed_count": 1,
        }
        result = qa_review_to_summary(raw)
        assert result["passes"] is False
        assert len(result["checks"]) == 1
        assert result["checks"][0]["suggestion"] == "Add more detail"

    def test_dict_input_empty_checks(self):
        raw = {"passes": True, "overall_feedback": "", "passed_count": 0, "failed_count": 0}
        result = qa_review_to_summary(raw)
        assert result["checks"] == []

    def test_dict_input_missing_keys_uses_defaults(self):
        raw = {}
        result = qa_review_to_summary(raw)
        assert result["passes"] is False
        assert result["overall_feedback"] == ""
        assert result["checks"] == []
        assert result["passed_count"] == 0
        assert result["failed_count"] == 0

    def test_dict_check_missing_fields_uses_defaults(self):
        raw = {
            "passes": True,
            "check_results": [{"requirement_id": "req-3"}],
            "passed_count": 1,
            "failed_count": 0,
        }
        result = qa_review_to_summary(raw)
        check = result["checks"][0]
        assert check["requirement_id"] == "req-3"
        assert check["passed"] is False  # default
        assert check["explanation"] == ""  # default
        assert check["severity"] == "critical"  # default
        assert check["suggestion"] is None  # default

    def test_pydantic_model_input(self):
        """Test with actual QAReview Pydantic model."""
        from src.models.draft import QAReview, QACheckResult

        review = QAReview(
            passes=True,
            overall_feedback="All good",
            check_results=[
                QACheckResult(
                    requirement_id="req-4",
                    passed=True,
                    explanation="Requirement met",
                    severity="critical",
                    suggestion=None,
                ),
                QACheckResult(
                    requirement_id="req-5",
                    passed=False,
                    explanation="Too short",
                    severity="warning",
                    suggestion="Expand the section",
                ),
            ],
        )
        result = qa_review_to_summary(review)
        assert result["passes"] is True
        assert result["overall_feedback"] == "All good"
        assert len(result["checks"]) == 2
        assert result["checks"][0]["requirement_id"] == "req-4"
        assert result["checks"][0]["passed"] is True
        assert result["checks"][1]["requirement_id"] == "req-5"
        assert result["checks"][1]["passed"] is False
        assert result["checks"][1]["suggestion"] == "Expand the section"
        assert result["passed_count"] == 1
        assert result["failed_count"] == 1

    def test_dict_and_pydantic_produce_same_shape(self):
        """Both input forms must produce identical output shape."""
        from src.models.draft import QAReview, QACheckResult

        check_data = {
            "requirement_id": "req-6",
            "passed": True,
            "explanation": "OK",
            "severity": "info",
            "suggestion": None,
        }

        dict_input = {
            "passes": True,
            "overall_feedback": "Fine",
            "check_results": [check_data],
            "passed_count": 1,
            "failed_count": 0,
        }

        model_input = QAReview(
            passes=True,
            overall_feedback="Fine",
            check_results=[QACheckResult(**check_data)],
        )

        dict_result = qa_review_to_summary(dict_input)
        model_result = qa_review_to_summary(model_input)

        assert dict_result == model_result
