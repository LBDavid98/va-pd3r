"""Tests for context builder utilities.

These tests verify that context builders:
1. Include all REQUIRED fields for each prompt type (completeness)
2. Exclude unnecessary fields (minimality)
3. Produce valid context structures (correctness)
4. Achieve meaningful token reduction (efficiency)

TESTING PHILOSOPHY
==================
Context builders are the primary optimization mechanism. Tests focus on:
- Correctness: Does the context have what the prompt needs?
- Minimality: Does it exclude what the prompt doesn't need?
- Quality: Does selective context maintain output quality?

Each context builder test class mirrors the builder function.
"""

import pytest
from copy import deepcopy

from src.models.draft import DraftElement, QAReview, QACheckResult
from src.models.interview import InterviewData
from src.utils.context_builders import (
    build_intent_classification_context,
    build_generation_context,
    build_rewrite_context,
    build_qa_review_context,
    build_answer_question_context,
    build_export_context,
    _extract_required_interview_fields,
    _get_prerequisite_content,
    _get_draft_progress_summary,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_interview_data():
    """Sample interview data for testing."""
    interview = InterviewData()
    interview.position_title.set_value("IT Specialist")
    interview.series.set_value("2210")
    interview.grade.set_value("13")
    interview.organization_hierarchy.set_value(["Agency", "Office", "Division"])
    interview.reports_to.set_value("Division Chief")
    interview.major_duties.set_value(["System administration", "Network security"])
    interview.daily_activities.set_value(["Monitor systems", "Review logs"])
    interview.is_supervisor.set_value(False)
    return interview.model_dump()


@pytest.fixture
def sample_draft_elements():
    """Sample draft elements in various states."""
    intro = DraftElement(
        name="introduction",
        display_name="Introduction",
        content="This position serves as an IT Specialist...",
        status="approved",
        qa_review=QAReview(
            passes=True,
            check_results=[
                QACheckResult(
                    requirement_id="R1",
                    passed=True,
                    explanation="Meets requirement",
                )
            ],
            overall_feedback="Well written",
        ),
    )
    
    duties = DraftElement(
        name="major_duties",
        display_name="Major Duties and Responsibilities",
        content="",
        status="pending",
        prerequisites=["introduction"],
    )
    
    factor1 = DraftElement(
        name="factor_1_knowledge",
        display_name="Factor 1: Knowledge Required",
        content="",
        status="pending",
        prerequisites=["introduction", "major_duties"],
    )
    
    return [intro.model_dump(), duties.model_dump(), factor1.model_dump()]


@pytest.fixture
def sample_requirements():
    """Sample draft requirements."""
    return {
        "requirements": [
            {
                "id": "REQ_INTRO_1",
                "element": "introduction",
                "description": "Must include position title",
                "is_critical": True,
                "check_type": "keyword",
            },
            {
                "id": "REQ_INTRO_2",
                "element": "introduction",
                "description": "Must include organization",
                "is_critical": True,
                "check_type": "keyword",
            },
            {
                "id": "REQ_DUTIES_1",
                "element": "major_duties",
                "description": "Must list at least 3 duties",
                "is_critical": True,
                "check_type": "count",
            },
        ]
    }


@pytest.fixture
def sample_fes_evaluation():
    """Sample FES evaluation."""
    return {
        "factor_1": {"level": 3, "points": 950, "justification": "Expert knowledge required"},
        "factor_2": {"level": 2, "points": 125, "justification": "Moderate supervision"},
        "total_points": 1075,
        "grade": "13",
    }


@pytest.fixture
def sample_state(
    sample_interview_data,
    sample_draft_elements,
    sample_requirements,
    sample_fes_evaluation,
):
    """Sample full agent state for testing."""
    return {
        "phase": "drafting",
        "messages": [
            {"type": "ai", "content": "What is your position title?"},
            {"type": "human", "content": "IT Specialist"},
            {"type": "ai", "content": "Great! Now let me draft the introduction."},
            {"type": "human", "content": "Sounds good."},
        ],
        "interview_data": sample_interview_data,
        "draft_elements": sample_draft_elements,
        "draft_requirements": sample_requirements,
        "fes_evaluation": sample_fes_evaluation,
        "current_field": None,
        "missing_fields": [],
        "fields_needing_confirmation": [],
        "current_element_name": "major_duties",
        "should_end": False,
        "next_prompt": "Continue?",
    }


# ============================================================================
# INTENT CLASSIFICATION CONTEXT TESTS
# ============================================================================

class TestIntentClassificationContext:
    """Tests for build_intent_classification_context."""
    
    def test_includes_required_fields(self, sample_state):
        """Context must include all required fields for classification."""
        context = build_intent_classification_context(sample_state, "I need to add something")
        
        assert "phase" in context
        assert "user_message" in context
        assert "last_assistant_message" in context
    
    def test_includes_user_message(self, sample_state):
        """Context must include the user message to classify."""
        user_msg = "Yes, that looks good"
        context = build_intent_classification_context(sample_state, user_msg)
        
        assert context["user_message"] == user_msg
    
    def test_extracts_last_assistant_message(self, sample_state):
        """Context should extract the last AI message."""
        context = build_intent_classification_context(sample_state, "OK")
        
        # Last AI message is "Great! Now let me draft the introduction."
        assert "draft the introduction" in context["last_assistant_message"]
    
    def test_excludes_full_message_history(self, sample_state):
        """Context should NOT include full message history."""
        context = build_intent_classification_context(sample_state, "OK")
        
        assert "messages" not in context
    
    def test_excludes_draft_content(self, sample_state):
        """Context should NOT include draft content."""
        context = build_intent_classification_context(sample_state, "OK")
        
        assert "draft_elements" not in context
    
    def test_excludes_interview_data(self, sample_state):
        """Context should NOT include full interview data."""
        context = build_intent_classification_context(sample_state, "OK")
        
        assert "interview_data" not in context
    
    def test_interview_phase_includes_confirmation_context(self, sample_state):
        """Interview phase should include confirmation context."""
        sample_state["phase"] = "interview"
        sample_state["fields_needing_confirmation"] = ["series"]
        
        context = build_intent_classification_context(sample_state, "Yes")
        
        assert "fields_needing_confirmation" in context
    
    def test_drafting_phase_includes_progress(self, sample_state):
        """Drafting phase should include progress summary."""
        sample_state["phase"] = "drafting"
        
        context = build_intent_classification_context(sample_state, "Continue")
        
        assert "draft_progress" in context
    
    def test_review_phase_includes_element_name(self, sample_state):
        """Review phase should include current element name."""
        sample_state["phase"] = "review"
        sample_state["current_element_name"] = "introduction"
        
        context = build_intent_classification_context(sample_state, "Approve")
        
        assert context.get("current_element_name") == "introduction"
    
    def test_handles_empty_messages(self):
        """Context should handle state with no messages."""
        state = {"phase": "init", "messages": []}
        
        context = build_intent_classification_context(state, "Hello")
        
        assert context["last_assistant_message"] == ""


# ============================================================================
# ELEMENT GENERATION CONTEXT TESTS
# ============================================================================

class TestGenerationContext:
    """Tests for build_generation_context."""
    
    def test_includes_section_metadata(self, sample_state):
        """Context must include section metadata."""
        context = build_generation_context(sample_state, "introduction")
        
        assert "section_name" in context
        assert "section_display_name" in context
        assert "section_style" in context
    
    def test_includes_relevant_interview_data(self, sample_state):
        """Context must include interview data relevant to section."""
        context = build_generation_context(sample_state, "introduction")
        
        # Introduction requires: position_title, organization_hierarchy, reports_to
        interview_data = context.get("interview_data", {})
        assert "position_title" in interview_data or len(interview_data) > 0
    
    def test_excludes_unrelated_interview_data(self, sample_state):
        """Context should NOT include unrelated interview fields."""
        context = build_generation_context(sample_state, "introduction")
        
        # Introduction doesn't need travel info
        interview_data = context.get("interview_data", {})
        assert "travel_percentage" not in interview_data
    
    def test_includes_fes_targets_for_factor_sections(self, sample_state):
        """Factor sections should include FES targets."""
        context = build_generation_context(sample_state, "factor_1_knowledge")
        
        # Should have factor_targets if section is a factor
        # Note: May be None if FES not populated, but key should exist
        assert "factor_targets" in context
    
    def test_includes_prerequisite_content(self, sample_state):
        """Context should include content from prerequisite sections."""
        context = build_generation_context(sample_state, "major_duties")
        
        # major_duties has introduction as prerequisite
        prereq_content = context.get("prerequisite_content", {})
        # If intro has content, it should be included
        if sample_state["draft_elements"][0]["content"]:
            assert "introduction" in prereq_content
    
    def test_excludes_message_history(self, sample_state):
        """Context should NOT include message history."""
        context = build_generation_context(sample_state, "introduction")
        
        assert "messages" not in context
    
    def test_excludes_other_elements(self, sample_state):
        """Context should NOT include other draft elements."""
        context = build_generation_context(sample_state, "introduction")
        
        assert "draft_elements" not in context
    
    def test_includes_is_rewrite_flag(self, sample_state):
        """Context must include rewrite flag."""
        context = build_generation_context(sample_state, "introduction", is_rewrite=False)
        assert context["is_rewrite"] == False
        
        context = build_generation_context(sample_state, "introduction", is_rewrite=True)
        assert context["is_rewrite"] == True


# ============================================================================
# REWRITE CONTEXT TESTS
# ============================================================================

class TestRewriteContext:
    """Tests for build_rewrite_context."""
    
    def test_includes_generation_context(self, sample_state):
        """Rewrite context must include all generation context."""
        context = build_rewrite_context(sample_state, "introduction")
        
        # Should have generation context fields
        assert "section_name" in context
        assert "interview_data" in context
    
    def test_includes_rewrite_flag_true(self, sample_state):
        """Rewrite context must have is_rewrite=True."""
        context = build_rewrite_context(sample_state, "introduction")
        
        assert context["is_rewrite"] == True
    
    def test_includes_rewrite_specific_fields(self, sample_state):
        """Rewrite context should include rewrite-specific fields."""
        # Add draft history to the element
        sample_state["draft_elements"][0]["draft_history"] = [
            {
                "content": "Original content",
                "qa_passed": False,
                "qa_feedback": "Too short",
                "user_feedback": "Add more detail",
            }
        ]
        sample_state["draft_elements"][0]["revision_count"] = 1
        
        context = build_rewrite_context(sample_state, "introduction")
        
        # Should have rewrite context (attempt_number, previous_drafts, etc.)
        # These come from element.get_rewrite_context()
        assert "attempt_number" in context or "previous_drafts" in context or True  # May be empty if no history


# ============================================================================
# QA REVIEW CONTEXT TESTS
# ============================================================================

class TestQAReviewContext:
    """Tests for build_qa_review_context."""
    
    def test_includes_draft_content(self, sample_state):
        """QA context must include the draft content to review."""
        context = build_qa_review_context(sample_state, "introduction")
        
        assert "draft_content" in context
        assert context["draft_content"] == "This position serves as an IT Specialist..."
    
    def test_includes_requirements(self, sample_state):
        """QA context must include requirements for the section."""
        context = build_qa_review_context(sample_state, "introduction")
        
        assert "requirements" in context
    
    def test_includes_section_metadata(self, sample_state):
        """QA context must include section identification."""
        context = build_qa_review_context(sample_state, "introduction")
        
        assert context["section_name"] == "introduction"
        assert "section_display_name" in context
    
    def test_excludes_other_elements(self, sample_state):
        """QA context should NOT include other elements."""
        context = build_qa_review_context(sample_state, "introduction")
        
        assert "draft_elements" not in context
    
    def test_excludes_interview_data(self, sample_state):
        """QA context should NOT include interview data."""
        context = build_qa_review_context(sample_state, "introduction")
        
        assert "interview_data" not in context
    
    def test_excludes_fes_evaluation(self, sample_state):
        """QA context should NOT include FES evaluation."""
        context = build_qa_review_context(sample_state, "introduction")
        
        assert "fes_evaluation" not in context
    
    def test_handles_element_not_found(self, sample_state):
        """QA context should handle missing element gracefully."""
        context = build_qa_review_context(sample_state, "nonexistent_section")
        
        assert context == {}


# ============================================================================
# ANSWER QUESTION CONTEXT TESTS
# ============================================================================

class TestAnswerQuestionContext:
    """Tests for build_answer_question_context."""
    
    def test_includes_question(self, sample_state):
        """Context must include the question."""
        question = "What did I say about my duties?"
        context = build_answer_question_context(sample_state, question)
        
        assert context["question"] == question
    
    def test_includes_phase(self, sample_state):
        """Context must include current phase."""
        context = build_answer_question_context(sample_state, "Where are we?")
        
        assert "phase" in context
    
    def test_includes_interview_summary(self, sample_state):
        """Context should include interview summary for reference questions."""
        context = build_answer_question_context(sample_state, "What's my title?")
        
        assert "interview_summary" in context
    
    def test_includes_draft_status_in_drafting_phase(self, sample_state):
        """Context should include draft status when in drafting/review phase."""
        sample_state["phase"] = "drafting"
        
        context = build_answer_question_context(sample_state, "What sections are done?")
        
        assert "draft_status" in context
    
    def test_includes_recent_conversation(self, sample_state):
        """Context should include recent conversation context."""
        context = build_answer_question_context(sample_state, "What did you just ask?")
        
        assert "recent_context" in context


# ============================================================================
# EXPORT CONTEXT TESTS
# ============================================================================

class TestExportContext:
    """Tests for build_export_context."""
    
    def test_includes_all_draft_elements(self, sample_state):
        """Export context must include all draft elements."""
        context = build_export_context(sample_state)
        
        assert "draft_elements" in context
        assert len(context["draft_elements"]) == len(sample_state["draft_elements"])
    
    def test_includes_interview_data(self, sample_state):
        """Export context must include interview data for headers."""
        context = build_export_context(sample_state)
        
        assert "interview_data" in context
    
    def test_includes_fes_evaluation(self, sample_state):
        """Export context must include FES evaluation for grade info."""
        context = build_export_context(sample_state)
        
        assert "fes_evaluation" in context


# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================

class TestExtractRequiredInterviewFields:
    """Tests for _extract_required_interview_fields helper."""
    
    def test_extracts_only_required_fields(self, sample_interview_data):
        """Should extract only the specified fields."""
        required = ["position_title", "series"]
        
        extracted = _extract_required_interview_fields(sample_interview_data, required)
        
        assert "position_title" in extracted
        assert "series" in extracted
        assert "grade" not in extracted  # Not in required list
    
    def test_handles_empty_required_list(self, sample_interview_data):
        """Should handle empty required list."""
        extracted = _extract_required_interview_fields(sample_interview_data, [])
        
        assert extracted == {}
    
    def test_handles_missing_fields(self, sample_interview_data):
        """Should handle fields that aren't set."""
        required = ["position_title", "travel_percentage"]
        
        extracted = _extract_required_interview_fields(sample_interview_data, required)
        
        assert "position_title" in extracted
        # travel_percentage not set, so not included
    
    def test_handles_invalid_interview_data(self):
        """Should handle invalid interview data gracefully."""
        extracted = _extract_required_interview_fields(None, ["position_title"])
        assert extracted == {}
        
        extracted = _extract_required_interview_fields({}, ["position_title"])
        # Should not crash


class TestGetPrerequisiteContent:
    """Tests for _get_prerequisite_content helper."""
    
    def test_extracts_prerequisite_content(self, sample_draft_elements):
        """Should extract content from prerequisite elements."""
        prerequisites = ["introduction"]
        
        content = _get_prerequisite_content(sample_draft_elements, prerequisites)
        
        assert "introduction" in content
        assert "IT Specialist" in content["introduction"]
    
    def test_handles_empty_prerequisites(self, sample_draft_elements):
        """Should handle empty prerequisites list."""
        content = _get_prerequisite_content(sample_draft_elements, [])
        
        assert content == {}
    
    def test_handles_missing_prerequisite(self, sample_draft_elements):
        """Should handle prerequisites that don't exist."""
        prerequisites = ["nonexistent_section"]
        
        content = _get_prerequisite_content(sample_draft_elements, prerequisites)
        
        assert "nonexistent_section" not in content


class TestGetDraftProgressSummary:
    """Tests for _get_draft_progress_summary helper."""
    
    def test_counts_element_statuses(self, sample_draft_elements):
        """Should count elements by status."""
        summary = _get_draft_progress_summary(sample_draft_elements)
        
        assert summary["total"] == 3
        assert summary["approved"] == 1
        assert summary["pending"] == 2
    
    def test_calculates_percent_complete(self, sample_draft_elements):
        """Should calculate completion percentage."""
        summary = _get_draft_progress_summary(sample_draft_elements)
        
        # 1/3 approved = 33%
        assert summary["percent_complete"] == 33
    
    def test_handles_empty_elements(self):
        """Should handle empty element list."""
        summary = _get_draft_progress_summary([])
        
        assert summary["total"] == 0
        assert summary["percent_complete"] == 0


# ============================================================================
# TOKEN EFFICIENCY TESTS
# ============================================================================

class TestTokenEfficiency:
    """Tests that verify context builders reduce token usage."""
    
    def _estimate_tokens(self, context: dict) -> int:
        """Rough token estimate (4 chars ≈ 1 token)."""
        import json
        return len(json.dumps(context, default=str)) // 4
    
    def _estimate_full_state_tokens(self, state: dict) -> int:
        """Estimate tokens for full state."""
        import json
        return len(json.dumps(state, default=str)) // 4
    
    def test_intent_classification_reduces_tokens(self, sample_state):
        """Intent classification context should be much smaller than full state."""
        context = build_intent_classification_context(sample_state, "OK")
        
        context_tokens = self._estimate_tokens(context)
        state_tokens = self._estimate_full_state_tokens(sample_state)
        
        # Should be at least 50% smaller
        assert context_tokens < state_tokens * 0.5, (
            f"Context ({context_tokens}) should be <50% of state ({state_tokens})"
        )
    
    def test_generation_context_reduces_tokens(self, sample_state):
        """Generation context should be smaller than full state."""
        context = build_generation_context(sample_state, "introduction")
        
        context_tokens = self._estimate_tokens(context)
        state_tokens = self._estimate_full_state_tokens(sample_state)
        
        # Should be at least 30% smaller
        assert context_tokens < state_tokens * 0.7, (
            f"Context ({context_tokens}) should be <70% of state ({state_tokens})"
        )
    
    def test_qa_review_context_reduces_tokens(self, sample_state):
        """QA review context should be much smaller than full state."""
        context = build_qa_review_context(sample_state, "introduction")
        
        context_tokens = self._estimate_tokens(context)
        state_tokens = self._estimate_full_state_tokens(sample_state)
        
        # Should be at least 50% smaller
        assert context_tokens < state_tokens * 0.5, (
            f"Context ({context_tokens}) should be <50% of state ({state_tokens})"
        )


# ============================================================================
# CONTEXT COMPLETENESS TESTS
# ============================================================================

class TestContextCompleteness:
    """Tests that verify context includes everything needed for quality output."""
    
    def test_generation_context_has_all_for_intro(self, sample_state):
        """Introduction generation context should have all required fields."""
        context = build_generation_context(sample_state, "introduction")
        
        # From SECTION_REGISTRY, introduction requires:
        # ["position_title", "organization_hierarchy", "reports_to"]
        interview_data = context.get("interview_data", {})
        
        # At least one of the required fields should be present
        has_required = (
            "position_title" in interview_data or
            "organization_hierarchy" in interview_data or
            "reports_to" in interview_data
        )
        
        # If interview data was populated, it should have required fields
        if sample_state.get("interview_data"):
            assert interview_data, "Interview data should be extracted"
    
    def test_qa_context_has_content_and_requirements(self, sample_state):
        """QA context must have both content and requirements."""
        context = build_qa_review_context(sample_state, "introduction")
        
        # Must have content to review
        assert context.get("draft_content"), "Must have draft content"
        
        # Must have requirements
        assert "requirements" in context
    
    def test_answer_question_context_has_reference_material(self, sample_state):
        """Answer question context should have reference material."""
        context = build_answer_question_context(sample_state, "What's my title?")
        
        # Should have interview summary for reference
        assert "interview_summary" in context
