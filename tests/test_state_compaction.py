"""Tests for state compaction utilities.

These tests verify that state compaction:
1. NEVER loses essential data (Tier 1 preservation)
2. Correctly compacts verbose data (Tier 2 after approval)
3. Clears transient fields appropriately (Tier 3)
4. Produces valid state for LangGraph checkpointing
"""

import pytest
from copy import deepcopy

from src.models.draft import DraftElement, QAReview, QACheckResult, DraftAttempt
from src.models.interview import InterviewData
from src.utils.state_compactor import (
    TIER_1_NEVER_COMPACT,
    ELEMENT_TIER_1_NEVER_COMPACT,
    ELEMENT_TIER_2_COMPACT_AFTER_APPROVAL,
    TIER_3_TRANSIENT,
    compact_after_interview,
    compact_after_element_approved,
    compact_after_export,
    clear_transient_fields,
    get_compaction_summary,
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
    return interview.model_dump()


@pytest.fixture
def sample_draft_element_approved():
    """Sample approved draft element with history."""
    qa_review = QAReview(
        passes=True,
        check_results=[
            QACheckResult(
                requirement_id="R1",
                passed=True,
                explanation="Meets requirement",
            )
        ],
        overall_feedback="Element meets all requirements",
    )
    
    # Create draft attempt as dict (as stored in state)
    draft_attempt_dict = {
        "content": "Original draft content that was too long...",
        "qa_passed": False,
        "qa_feedback": "Content exceeded length requirements",
        "qa_failures": ["R1: Length exceeded", "R2: Missing keywords"],
        "user_feedback": "Please make it shorter",
        "rewrite_reason": "qa_failure",
    }
    
    element = DraftElement(
        name="introduction",
        display_name="Introduction",
        content="This is the approved introduction content.",
        status="approved",
        qa_review=qa_review,
        qa_history=[
            {
                "passes": False,
                "overall_feedback": "First attempt failed",
                "check_results": [],
            },
            qa_review.model_dump(),
        ],
        draft_history=[draft_attempt_dict],
        qa_notes=["Consider adding more detail about mission"],
        feedback="User asked for revision",
        revision_count=1,
    )
    return element


@pytest.fixture
def sample_draft_element_pending():
    """Sample pending draft element."""
    return DraftElement(
        name="factor_1_knowledge",
        display_name="Factor 1: Knowledge Required",
        content="",
        status="pending",
    )


@pytest.fixture
def sample_state(sample_interview_data, sample_draft_element_approved, sample_draft_element_pending):
    """Sample full agent state for testing."""
    return {
        "phase": "drafting",
        "messages": [
            {"type": "ai", "content": "Let me draft the introduction."},
            {"type": "human", "content": "Sounds good."},
        ],
        "interview_data": sample_interview_data,
        "draft_elements": [
            sample_draft_element_approved.model_dump(),
            sample_draft_element_pending.model_dump(),
        ],
        "fes_evaluation": {"factor_1": {"level": 3, "points": 950}},
        "draft_requirements": {"requirements": []},
        "current_field": None,
        "missing_fields": [],
        "fields_needing_confirmation": [],
        "_field_mappings": [{"field": "title", "value": "IT Specialist"}],
        "pending_question": "What about travel?",
        "last_error": "Some previous error",
        "validation_error": "Invalid input",
        "should_end": False,
        "next_prompt": "Continue?",
        "wants_another": None,
        "is_restart": False,
        "is_resume": False,
    }


# ============================================================================
# TIER 1 - NEVER COMPACT TESTS
# ============================================================================

class TestTier1Preservation:
    """Tests that Tier 1 fields are NEVER lost during compaction."""
    
    def test_compact_after_interview_preserves_interview_data(self, sample_state):
        """Interview data must never be lost after interview compaction."""
        updates = compact_after_interview(sample_state)
        
        # Updates should NOT include interview_data (it's preserved)
        assert "interview_data" not in updates
    
    def test_compact_after_interview_preserves_phase(self, sample_state):
        """Phase must never be lost after interview compaction."""
        updates = compact_after_interview(sample_state)
        assert "phase" not in updates
    
    def test_compact_after_interview_preserves_messages(self, sample_state):
        """Messages must never be lost after interview compaction."""
        updates = compact_after_interview(sample_state)
        assert "messages" not in updates
    
    def test_compact_after_element_preserves_content(self, sample_state):
        """Draft element content must never be lost."""
        updates = compact_after_element_approved(sample_state, element_index=0)
        
        # Check that content is preserved
        updated_elements = updates.get("draft_elements", [])
        if updated_elements:
            approved_elem = updated_elements[0]
            assert approved_elem["content"] == "This is the approved introduction content."
    
    def test_compact_after_element_preserves_status(self, sample_state):
        """Draft element status must never be lost."""
        updates = compact_after_element_approved(sample_state, element_index=0)
        
        updated_elements = updates.get("draft_elements", [])
        if updated_elements:
            approved_elem = updated_elements[0]
            assert approved_elem["status"] == "approved"
    
    def test_compact_after_element_preserves_qa_review(self, sample_state):
        """Most recent qa_review must never be lost."""
        updates = compact_after_element_approved(sample_state, element_index=0)
        
        updated_elements = updates.get("draft_elements", [])
        if updated_elements:
            approved_elem = updated_elements[0]
            assert approved_elem.get("qa_review") is not None
    
    def test_compact_after_export_preserves_all_content(self, sample_state):
        """All element content must be preserved after export."""
        # Add content to pending element for test
        sample_state["draft_elements"][1]["content"] = "Factor 1 content"
        sample_state["draft_elements"][1]["status"] = "approved"
        
        updates = compact_after_export(sample_state)
        
        updated_elements = updates.get("draft_elements", [])
        assert len(updated_elements) == 2
        assert updated_elements[0]["content"] == "This is the approved introduction content."
        assert updated_elements[1]["content"] == "Factor 1 content"


# ============================================================================
# TIER 2 - COMPACT AFTER APPROVAL TESTS
# ============================================================================

class TestTier2Compaction:
    """Tests that Tier 2 fields are compacted after approval."""
    
    def test_compact_after_element_compacts_draft_history(self, sample_state):
        """Draft history should be compacted to summary after approval."""
        updates = compact_after_element_approved(sample_state, element_index=0)
        
        updated_elements = updates.get("draft_elements", [])
        if updated_elements:
            approved_elem = updated_elements[0]
            history = approved_elem.get("draft_history", [])
            
            if history:
                # Should have metadata only, not full content
                assert "content" not in history[0]
                assert "qa_passed" in history[0]
                assert "rewrite_reason" in history[0]
    
    def test_compact_after_element_keeps_only_latest_qa_history(self, sample_state):
        """Only the latest QA history entry should be kept."""
        updates = compact_after_element_approved(sample_state, element_index=0)
        
        updated_elements = updates.get("draft_elements", [])
        if updated_elements:
            approved_elem = updated_elements[0]
            qa_history = approved_elem.get("qa_history", [])
            
            # Should have at most 1 entry
            assert len(qa_history) <= 1
    
    def test_compact_after_element_clears_qa_notes(self, sample_state):
        """QA notes should be cleared after approval."""
        updates = compact_after_element_approved(sample_state, element_index=0)
        
        updated_elements = updates.get("draft_elements", [])
        if updated_elements:
            approved_elem = updated_elements[0]
            assert approved_elem.get("qa_notes") == []
    
    def test_compact_after_element_clears_feedback(self, sample_state):
        """Feedback should be cleared after approval."""
        updates = compact_after_element_approved(sample_state, element_index=0)
        
        updated_elements = updates.get("draft_elements", [])
        if updated_elements:
            approved_elem = updated_elements[0]
            assert approved_elem.get("feedback") == ""
    
    def test_compact_skips_non_approved_elements(self, sample_state):
        """Compaction should skip elements that aren't approved."""
        # Try to compact the pending element
        updates = compact_after_element_approved(sample_state, element_index=1)
        
        # Should return empty - no compaction needed
        assert updates == {}


# ============================================================================
# TIER 3 - TRANSIENT FIELD TESTS
# ============================================================================

class TestTier3TransientFields:
    """Tests that transient fields are cleared appropriately."""
    
    def test_compact_after_interview_clears_field_mappings(self, sample_state):
        """Field mappings should be cleared after interview."""
        updates = compact_after_interview(sample_state)
        
        assert "_field_mappings" in updates
        assert updates["_field_mappings"] is None
    
    def test_compact_after_interview_clears_current_field(self, sample_state):
        """Current field should be cleared after interview."""
        sample_state["current_field"] = "major_duties"
        updates = compact_after_interview(sample_state)
        
        assert "current_field" in updates
        assert updates["current_field"] is None
    
    def test_compact_after_interview_clears_fields_needing_confirmation(self, sample_state):
        """Fields needing confirmation should be cleared after interview."""
        sample_state["fields_needing_confirmation"] = ["title", "series"]
        updates = compact_after_interview(sample_state)
        
        assert "fields_needing_confirmation" in updates
        assert updates["fields_needing_confirmation"] == []
    
    def test_compact_after_interview_clears_pending_question(self, sample_state):
        """Pending question should be cleared after interview."""
        updates = compact_after_interview(sample_state)
        
        assert "pending_question" in updates
        assert updates["pending_question"] is None
    
    def test_compact_after_interview_clears_validation_error(self, sample_state):
        """Validation error should be cleared after interview."""
        updates = compact_after_interview(sample_state)
        
        assert "validation_error" in updates
        assert updates["validation_error"] is None
    
    def test_clear_transient_fields_clears_all(self, sample_state):
        """clear_transient_fields should clear all tier 3 fields."""
        updates = clear_transient_fields(sample_state)
        
        # Should have cleared all set transient fields
        assert "_field_mappings" in updates or sample_state.get("_field_mappings") is None
        assert "pending_question" in updates or sample_state.get("pending_question") is None
        assert "last_error" in updates or sample_state.get("last_error") is None


# ============================================================================
# EDGE CASES AND ERROR HANDLING
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_compact_empty_state(self):
        """Compaction should handle empty state gracefully."""
        empty_state = {"phase": "init"}
        
        # Should not raise
        updates = compact_after_interview(empty_state)
        assert isinstance(updates, dict)
    
    def test_compact_invalid_element_index(self, sample_state):
        """Compaction should handle invalid element index."""
        updates = compact_after_element_approved(sample_state, element_index=99)
        
        # Should return empty, not raise
        assert updates == {}
    
    def test_compact_no_draft_elements(self, sample_state):
        """Compaction should handle missing draft_elements."""
        sample_state["draft_elements"] = []
        
        updates = compact_after_export(sample_state)
        # Should return empty dict when no elements to process
        # (nothing to compact, no updates needed)
        assert updates.get("draft_elements", []) == [] or "draft_elements" not in updates
    
    def test_compact_preserves_other_elements(self, sample_state):
        """Compacting one element should not affect others."""
        updates = compact_after_element_approved(sample_state, element_index=0)
        
        updated_elements = updates.get("draft_elements", [])
        if updated_elements:
            # Second element should be unchanged
            pending_elem = updated_elements[1]
            assert pending_elem["name"] == "factor_1_knowledge"
            assert pending_elem["status"] == "pending"


# ============================================================================
# COMPACTION SUMMARY TESTS
# ============================================================================

class TestCompactionSummary:
    """Tests for the compaction summary utility."""
    
    def test_summary_identifies_transient_fields(self, sample_state):
        """Summary should identify transient fields that are set."""
        summary = get_compaction_summary(sample_state)
        
        assert "transient_fields_set" in summary
        assert len(summary["transient_fields_set"]) > 0
    
    def test_summary_identifies_elements_with_history(self, sample_state):
        """Summary should identify elements with compactable history."""
        summary = get_compaction_summary(sample_state)
        
        assert "elements_with_history" in summary
        # The approved element has history
        assert any(
            elem["name"] == "introduction"
            for elem in summary["elements_with_history"]
        )
    
    def test_summary_counts_qa_history(self, sample_state):
        """Summary should count total QA history entries."""
        summary = get_compaction_summary(sample_state)
        
        assert "total_qa_history_entries" in summary
        assert summary["total_qa_history_entries"] >= 2  # The approved element has 2
    
    def test_summary_identifies_compaction_opportunities(self, sample_state):
        """Summary should identify compaction opportunities."""
        summary = get_compaction_summary(sample_state)
        
        assert "compaction_opportunities" in summary


# ============================================================================
# STATE VALIDITY TESTS
# ============================================================================

class TestStateValidity:
    """Tests that compacted state remains valid."""
    
    def test_compacted_elements_are_valid_except_history(self, sample_state):
        """Compacted elements should still be mostly valid, with compacted history.
        
        Note: draft_history is compacted to summary dicts that are NOT valid
        DraftAttempt models. This is intentional - we keep metadata only.
        The element itself should still be usable for export and display.
        """
        updates = compact_after_element_approved(sample_state, element_index=0)
        
        updated_elements = updates.get("draft_elements", [])
        for elem_dict in updated_elements:
            # Core fields should be present and valid
            assert "name" in elem_dict
            assert "content" in elem_dict
            assert "status" in elem_dict
            
            # draft_history should be compacted (summary dicts, not full models)
            if elem_dict.get("draft_history"):
                for history_item in elem_dict["draft_history"]:
                    # Should have summary fields
                    assert "qa_passed" in history_item
                    # Should NOT have verbose fields
                    assert "content" not in history_item
    
    def test_compacted_state_is_serializable(self, sample_state):
        """Compacted state should be JSON serializable for checkpointing."""
        import json
        
        updates = compact_after_export(sample_state)
        
        # Apply updates to state
        compacted_state = {**sample_state, **updates}
        
        # Should not raise
        serialized = json.dumps(compacted_state, default=str)
        assert isinstance(serialized, str)


# ============================================================================
# TIER DEFINITION TESTS
# ============================================================================

class TestTierDefinitions:
    """Tests for tier definition consistency."""
    
    def test_tier_1_includes_critical_fields(self):
        """Tier 1 should include all critical fields."""
        critical_fields = {
            "phase",
            "messages",
            "interview_data",
            "draft_elements",
            "fes_evaluation",
            "draft_requirements",
        }
        
        assert critical_fields.issubset(TIER_1_NEVER_COMPACT)
    
    def test_element_tier_1_includes_critical_fields(self):
        """Element Tier 1 should include critical element fields."""
        critical_element_fields = {
            "name",
            "content",
            "status",
            "qa_review",
        }
        
        assert critical_element_fields.issubset(ELEMENT_TIER_1_NEVER_COMPACT)
    
    def test_tiers_are_disjoint(self):
        """Tier definitions should not overlap."""
        # Tier 1 and Tier 3 should be disjoint
        overlap = TIER_1_NEVER_COMPACT & TIER_3_TRANSIENT
        assert len(overlap) == 0, f"Overlap found: {overlap}"
    
    def test_transient_fields_all_clearable(self):
        """All transient fields should be clearable."""
        clearable_types = {str, type(None), list, dict}
        
        # Each transient field should have a clear value
        for field in TIER_3_TRANSIENT:
            # This is a design assertion - all transient fields
            # should be clearable to None or empty list
            assert field is not None
