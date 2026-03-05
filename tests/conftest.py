"""Pytest configuration and fixtures.

Note: LLM tests are skipped by default. Run with:
    pytest -m llm          # Run ONLY LLM tests
    pytest -m 'not llm'    # Run all EXCEPT LLM tests (default)
    pytest -m ''           # Run ALL tests including LLM
"""

import os
import pytest
from pathlib import Path

# Load .env FIRST before any test modules check for API keys
from dotenv import load_dotenv
load_dotenv()


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "llm: tests that require real LLM calls (skipped by default)"
    )
    config.addinivalue_line(
        "markers", "llm_integration: integration tests with LLM (subset of llm)"
    )
    config.addinivalue_line(
        "markers", "llm_e2e: end-to-end tests with LLM"
    )


@pytest.fixture(scope="session", autouse=True)
def export_graph_on_test():
    """Export graph visualization after test session."""
    yield

    # Export graph after tests complete
    try:
        from src.graphs import pd_graph
        from src.graphs.export import export_graph

        export_graph(pd_graph, "output/graphs", "main_graph")
    except ImportError:
        pass  # Skip if not fully set up


@pytest.fixture
def skip_without_api_key():
    """Skip test if OPENAI_API_KEY is not set."""
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set - skipping LLM test")


@pytest.fixture
def sample_state():
    """Sample agent state for testing."""
    return {
        "messages": [],
        "phase": "init",
        "interview_data": None,
        "current_field": None,
        "missing_fields": [],
        "fields_needing_confirmation": [],
        "last_intent": None,
        "pending_question": None,
        "draft_requirements": None,
        "draft_elements": [],
        "current_element_index": 0,
        "current_element_name": None,
        "should_end": False,
        "next_prompt": "",
        "fes_evaluation": None,
        "wants_another": None,
        "is_restart": False,
        "is_resume": False,
        "validation_error": None,
        "last_error": None,
    }


@pytest.fixture
def interview_data_fixture():
    """Sample InterviewData for testing."""
    from src.models.interview import InterviewData

    data = InterviewData()
    data.position_title.set_value("IT Specialist")
    data.series.set_value("2210")
    data.grade.set_value("GS-13")
    return data
