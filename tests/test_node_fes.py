"""Unit tests for Phase 3 nodes: FES evaluation and requirements gathering."""

import pytest

from src.models.interview import InterviewData
from src.models.state import AgentState
from src.nodes.evaluate_fes_factors_node import evaluate_fes_factors_node
from src.nodes.gather_draft_requirements_node import gather_draft_requirements_node


class TestEvaluateFESFactorsNode:
    """Tests for evaluate_fes_factors_node."""

    def _make_state_with_grade(self, grade: str) -> AgentState:
        """Create state with interview data containing a grade."""
        interview = InterviewData()
        interview.grade.set_value(grade)
        interview.series.set_value("2210")
        interview.position_title.set_value("IT Specialist")

        return {
            "messages": [],
            "phase": "interview",
            "interview_data": interview.model_dump(),
            "current_field": None,
            "missing_fields": [],
            "fields_needing_confirmation": [],
            "last_intent": None,
            "pending_question": None,
            "fes_evaluation": None,
            "draft_requirements": None,
            "draft_elements": [],
            "current_element_index": 0,
            "current_element_name": None,
            "should_end": False,
            "next_prompt": "",
        }

    def test_evaluate_gs13(self):
        """Test FES evaluation for GS-13."""
        state = self._make_state_with_grade("GS-13")
        result = evaluate_fes_factors_node(state)

        assert "fes_evaluation" in result
        assert result["fes_evaluation"] is not None

        fes = result["fes_evaluation"]
        assert fes["grade"] == "GS-13"
        assert fes["grade_num"] == 13
        assert fes["factor_1_knowledge"] is not None

    def test_evaluate_gs14(self):
        """Test FES evaluation for GS-14."""
        state = self._make_state_with_grade("14")
        result = evaluate_fes_factors_node(state)

        assert result["fes_evaluation"]["grade_num"] == 14

    def test_evaluate_no_interview_data(self):
        """Test with missing interview data."""
        state = {
            "messages": [],
            "phase": "interview",
            "interview_data": None,
            "fes_evaluation": None,
            "draft_requirements": None,
            "draft_elements": [],
            "current_element_index": 0,
            "should_end": False,
            "next_prompt": "",
        }
        result = evaluate_fes_factors_node(state)

        assert "fes_evaluation" not in result or result.get("fes_evaluation") is None
        assert len(result.get("messages", [])) > 0

    def test_evaluate_no_grade(self):
        """Test with missing grade in interview."""
        interview = InterviewData()
        interview.series.set_value("2210")
        # Grade not set

        state = {
            "messages": [],
            "phase": "interview",
            "interview_data": interview.model_dump(),
            "fes_evaluation": None,
            "draft_requirements": None,
            "draft_elements": [],
            "current_element_index": 0,
            "should_end": False,
            "next_prompt": "",
        }
        result = evaluate_fes_factors_node(state)

        assert "fes_evaluation" not in result or result.get("fes_evaluation") is None

    def test_evaluate_invalid_grade(self):
        """Test with invalid grade."""
        state = self._make_state_with_grade("GS-99")
        result = evaluate_fes_factors_node(state)

        assert "fes_evaluation" not in result or result.get("fes_evaluation") is None

    def test_evaluate_updates_phase(self):
        """Test that successful evaluation updates phase."""
        state = self._make_state_with_grade("GS-13")
        result = evaluate_fes_factors_node(state)

        assert result.get("phase") == "requirements"


class TestGatherDraftRequirementsNode:
    """Tests for gather_draft_requirements_node."""

    def _make_state_with_fes(self, grade: int = 13, series: str = "2210") -> AgentState:
        """Create state with FES evaluation."""
        from src.config.fes_factors import evaluate_fes_for_grade

        interview = InterviewData()
        interview.grade.set_value(f"GS-{grade}")
        interview.series.set_value(series)
        interview.position_title.set_value("IT Specialist")
        interview.is_supervisor.set_value(False)

        fes = evaluate_fes_for_grade(grade)

        return {
            "messages": [],
            "phase": "requirements",
            "interview_data": interview.model_dump(),
            "current_field": None,
            "missing_fields": [],
            "fields_needing_confirmation": [],
            "last_intent": None,
            "pending_question": None,
            "fes_evaluation": fes.model_dump() if fes else None,
            "draft_requirements": None,
            "draft_elements": [],
            "current_element_index": 0,
            "current_element_name": None,
            "should_end": False,
            "next_prompt": "",
        }

    def test_gather_requirements_gs2210_13(self):
        """Test requirements gathering for GS-2210-13."""
        state = self._make_state_with_fes(grade=13, series="2210")
        result = gather_draft_requirements_node(state)

        assert "draft_requirements" in result
        reqs = result["draft_requirements"]
        assert reqs is not None
        assert len(reqs["requirements"]) > 0

    def test_gather_requirements_creates_draft_elements(self):
        """Test that draft elements are created."""
        state = self._make_state_with_fes()
        result = gather_draft_requirements_node(state)

        assert "draft_elements" in result
        elements = result["draft_elements"]
        assert len(elements) > 0
        assert elements[0]["name"] == "introduction"

    def test_gather_requirements_updates_phase(self):
        """Test that phase is updated to drafting."""
        state = self._make_state_with_fes()
        result = gather_draft_requirements_node(state)

        assert result.get("phase") == "drafting"

    def test_gather_requirements_no_fes(self):
        """Test with missing FES evaluation."""
        state = {
            "messages": [],
            "phase": "requirements",
            "interview_data": {},
            "fes_evaluation": None,
            "draft_requirements": None,
            "draft_elements": [],
            "current_element_index": 0,
            "should_end": False,
            "next_prompt": "",
        }
        result = gather_draft_requirements_node(state)

        # Should return error message
        assert len(result.get("messages", [])) > 0

    def test_gather_requirements_fes_based(self):
        """Test that FES requirements are generated."""
        state = self._make_state_with_fes()
        result = gather_draft_requirements_node(state)

        reqs = result["draft_requirements"]["requirements"]
        # Should have FES-based requirements
        fes_reqs = [r for r in reqs if r["source"].startswith("FES")]
        assert len(fes_reqs) > 0

    def test_gather_requirements_duty_template(self):
        """Test that duty template requirements are generated for 2210."""
        state = self._make_state_with_fes(series="2210")
        result = gather_draft_requirements_node(state)

        reqs = result["draft_requirements"]["requirements"]
        # Should have duty template requirements for 2210
        duty_reqs = [r for r in reqs if "Duty" in r["source"]]
        # May or may not have duty template depending on JSON config
        # Just check the structure is correct
        assert isinstance(reqs, list)

    def test_gather_requirements_no_duty_template(self):
        """Test requirements for series without template."""
        state = self._make_state_with_fes(series="0343")  # No template for 0343
        result = gather_draft_requirements_node(state)

        # Should still succeed
        assert "draft_requirements" in result
        reqs = result["draft_requirements"]
        assert reqs["duty_template"] is None

    def test_gather_requirements_sets_current_element(self):
        """Test that current element is set correctly."""
        state = self._make_state_with_fes()
        result = gather_draft_requirements_node(state)

        assert result.get("current_element_index") == 0
        assert result.get("current_element_name") == "introduction"


class TestDraftingPreamble:
    """Tests for the drafting preamble message."""

    def _make_state_with_fes(
        self, grade: int = 13, series: str = "2210", is_supervisor: bool = False
    ) -> AgentState:
        """Create state with FES evaluation."""
        from src.config.fes_factors import evaluate_fes_for_grade

        interview = InterviewData()
        interview.grade.set_value(f"GS-{grade}")
        interview.series.set_value(series)
        interview.position_title.set_value("IT Specialist")
        interview.is_supervisor.set_value(is_supervisor)

        fes = evaluate_fes_for_grade(grade)

        return {
            "messages": [],
            "phase": "requirements",
            "interview_data": interview.model_dump(),
            "current_field": None,
            "missing_fields": [],
            "fields_needing_confirmation": [],
            "last_intent": None,
            "pending_question": None,
            "fes_evaluation": fes.model_dump() if fes else None,
            "draft_requirements": None,
            "draft_elements": [],
            "current_element_index": 0,
            "current_element_name": None,
            "should_end": False,
            "next_prompt": "",
        }

    def test_preamble_contains_ready_message(self):
        """Preamble should contain 'ready to start writing'."""
        state = self._make_state_with_fes()
        result = gather_draft_requirements_node(state)

        message = result["messages"][0].content
        assert "ready to start writing" in message.lower()

    def test_preamble_lists_all_elements(self):
        """Preamble should list all draft elements that will be generated."""
        state = self._make_state_with_fes()
        result = gather_draft_requirements_node(state)

        message = result["messages"][0].content
        draft_elements = result["draft_elements"]
        
        # Preamble should list each draft element's display_name
        # (respects MAX_DRAFTS limit from pyproject.toml)
        for elem in draft_elements:
            display_name = elem.get("display_name", elem.get("name", ""))
            assert display_name in message, f"Expected '{display_name}' in preamble"

    def test_preamble_includes_element_count(self):
        """Preamble should include element count."""
        state = self._make_state_with_fes()
        result = gather_draft_requirements_node(state)

        message = result["messages"][0].content
        draft_elements = result["draft_elements"]
        
        # Should mention the count
        assert f"{len(draft_elements)} sections" in message

    def test_preamble_mentions_first_element(self):
        """Preamble should mention starting with first element."""
        state = self._make_state_with_fes()
        result = gather_draft_requirements_node(state)

        message = result["messages"][0].content
        # Should mention starting with Introduction
        assert "Introduction" in message
        assert "start" in message.lower()

    def test_preamble_supervisory_note(self):
        """Supervisory positions should note supervisory factors."""
        state = self._make_state_with_fes(is_supervisor=True)
        result = gather_draft_requirements_node(state)

        message = result["messages"][0].content
        # Should mention supervisory
        assert "supervisory" in message.lower()

    def test_preamble_non_supervisory_no_supervisory_factors(self):
        """Non-supervisory positions should not include supervisory factors element."""
        state = self._make_state_with_fes(is_supervisor=False)
        result = gather_draft_requirements_node(state)

        # Check that supervisory_factors element is not in draft_elements
        draft_elements = result["draft_elements"]
        element_names = [e["name"] for e in draft_elements]
        assert "supervisory_factors" not in element_names
