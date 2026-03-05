"""Test configuration for simplified e2e testing.

Provides a minimal interview configuration and single-element draft
for faster end-to-end test execution.
"""

from typing import Any

from src.config.intake_fields import IntakeField


# Minimal fields for test interview - enough to test flow, not full content
MINIMAL_INTAKE_FIELDS: dict[str, dict[str, Any]] = {
    "position_title": {
        "prompt": "Enter the position title",
        "user_guidance": "What is the official title for this position?",
        "field_type": "string",
        "required": True,
        "category": "core_metadata",
        "examples": ["Data Scientist"],
        "placeholder": "Position title",
        "sequence_weight": 10,
    },
    "series": {
        "prompt": "Enter the job series (e.g., 2210)",
        "user_guidance": "What OPM series code?",
        "field_type": "string",
        "required": True,
        "category": "core_metadata",
        "examples": ["2210"],
        "placeholder": "Series code",
        "sequence_weight": 20,
    },
    "grade": {
        "prompt": "Enter the grade (11-15)",
        "user_guidance": "What target GS grade?",
        "field_type": "string",
        "required": True,
        "category": "core_metadata",
        "examples": ["13"],
        "placeholder": "Grade",
        "sequence_weight": 30,
        "validation": {"choices": ["11", "12", "13", "14", "15"]},
    },
    "major_duties": {
        "prompt": "List 2-3 major duties with time percentages",
        "user_guidance": "What are the main duties?",
        "field_type": "dict",
        "required": True,
        "category": "duties",
        "examples": ["Lead projects 50%; Support team 50%"],
        "placeholder": "Duty: percentage",
        "sequence_weight": 40,
        "validation": {"total_percentage": 100},
    },
}

# Parsed as IntakeField models
MINIMAL_INTAKE_FIELDS_PARSED: dict[str, IntakeField] = {
    name: IntakeField(**config)
    for name, config in sorted(
        MINIMAL_INTAKE_FIELDS.items(),
        key=lambda item: item[1].get("sequence_weight", 0),
    )
}

# Minimal sequence for test
MINIMAL_INTAKE_SEQUENCE: list[str] = [
    "position_title",
    "series",
    "grade",
    "major_duties",
]

# Minimal draft elements for testing - just introduction
MINIMAL_DRAFT_ELEMENT_NAMES: list[str] = [
    "introduction",
]

MINIMAL_DRAFT_ELEMENT_DISPLAY_NAMES: dict[str, str] = {
    "introduction": "Introduction",
}


# Pre-defined test answers for automated testing (minimal interview only)
TEST_ANSWERS: dict[str, str] = {
    "position_title": "Senior Data Scientist",
    "series": "1560",
    "grade": "13",
    "major_duties": "Lead data analysis projects 50%; Develop ML models 30%; Stakeholder briefings 20%",
}

# Full test answers for complete non-supervisory interview (all BASE_INTAKE_SEQUENCE fields)
FULL_TEST_ANSWERS: dict[str, str] = {
    "position_title": "Senior Data Scientist",
    "series": "1560",
    "grade": "13",
    "organization_hierarchy": "Department of Commerce, Bureau of Economic Analysis, Data Analytics Division",
    "reports_to": "Chief Data Officer",
    "daily_activities": "Analyze large datasets using Python and SQL; Build and maintain predictive models; Create data visualizations and dashboards; Collaborate with program offices on data requirements; Document analytical methodologies",
    "major_duties": "Lead enterprise data analytics initiatives 40%; Develop and deploy machine learning models 35%; Provide data-driven insights to senior leadership 25%",
    "is_supervisor": "no",
}


# Expected flow events for validation
class TestFlowExpectations:
    """Expectations for automated test validation."""
    
    MIN_INTERVIEW_QUESTIONS = len(MINIMAL_INTAKE_SEQUENCE)
    EXPECTED_PHASES = ["init", "interview", "requirements", "drafting"]
    
    @classmethod
    def get_answer_for_field(cls, field_name: str) -> str:
        """Get the test answer for a field."""
        return TEST_ANSWERS.get(field_name, "test answer")
