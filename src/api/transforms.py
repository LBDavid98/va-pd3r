"""Data transformations for the API layer.

Provides single-source-of-truth functions for converting internal models
to API response shapes. Used by both WebSocket streaming and REST endpoints.
"""

from __future__ import annotations

from typing import Any


def qa_review_to_summary(raw_qa: Any) -> dict | None:
    """Transform a QA review into the frontend summary shape.

    Handles two input forms:
    - **dict** (from graph streaming events): keys like "check_results" or "checks"
    - **QAReview Pydantic model** (from DraftElement.model_validate): typed attributes

    Returns:
        Frontend-shaped dict with keys: passes, overall_feedback, checks,
        passed_count, failed_count. Returns None if raw_qa is None/falsy.
    """
    if raw_qa is None:
        return None

    # Extract fields — support both dict and Pydantic model
    if isinstance(raw_qa, dict):
        passes = raw_qa.get("passes", False)
        overall_feedback = raw_qa.get("overall_feedback", "")
        # Streaming events may use "check_results" or "checks"
        checks_raw = raw_qa.get("check_results") or raw_qa.get("checks") or []
        passed_count = raw_qa.get("passed_count", 0)
        failed_count = raw_qa.get("failed_count", 0)
    else:
        # Pydantic QAReview model
        passes = raw_qa.passes
        overall_feedback = raw_qa.overall_feedback
        checks_raw = raw_qa.check_results
        passed_count = raw_qa.passed_count
        failed_count = raw_qa.failed_count

    # Normalize checks to list of dicts
    checks = []
    for c in checks_raw:
        if isinstance(c, dict):
            checks.append({
                "requirement_id": c.get("requirement_id", ""),
                "passed": c.get("passed", False),
                "explanation": c.get("explanation", ""),
                "severity": c.get("severity", "critical"),
                "suggestion": c.get("suggestion"),
            })
        else:
            # Pydantic QACheckResult model
            checks.append({
                "requirement_id": c.requirement_id,
                "passed": c.passed,
                "explanation": c.explanation,
                "severity": c.severity,
                "suggestion": c.suggestion,
            })

    return {
        "passes": passes,
        "overall_feedback": overall_feedback,
        "checks": checks,
        "passed_count": passed_count,
        "failed_count": failed_count,
    }
