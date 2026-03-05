"""Tests for QA (Quality Assurance) tools.

These tests verify the QA tool wrappers work correctly.
Per ADR-005, we use real LLM calls where needed (marked with @pytest.mark.llm).
"""

import pytest
from unittest.mock import MagicMock, patch

from src.tools.qa_tools import (
    QA_TOOLS,
    QA_PASS_THRESHOLD,
    QA_REWRITE_THRESHOLD,
    MAX_REWRITES,
    _build_qa_context,
    _convert_schema_to_model,
    check_qa_status,
    get_qa_thresholds,
    qa_review_section,
    request_qa_rewrite,
    request_section_approval,
    QACheckResultSchema,
    QAReviewSchema,
)
from src.models.draft import DraftElement, QAReview, QACheckResult
from src.models.requirements import DraftRequirement, DraftRequirements


# =============================================================================
# THRESHOLD CONSTANTS TESTS
# =============================================================================

class TestThresholdConstants:
    """Test QA threshold constants are properly set."""
    
    def test_pass_threshold(self):
        """Pass threshold is reasonable."""
        assert 0 < QA_PASS_THRESHOLD <= 1
        assert QA_PASS_THRESHOLD == 0.8
    
    def test_rewrite_threshold(self):
        """Rewrite threshold is below pass threshold."""
        assert QA_REWRITE_THRESHOLD < QA_PASS_THRESHOLD
        assert QA_REWRITE_THRESHOLD == 0.5
    
    def test_max_rewrites(self):
        """Max rewrites is positive integer."""
        assert MAX_REWRITES >= 1
        assert MAX_REWRITES == 1


# =============================================================================
# HELPER FUNCTION TESTS
# =============================================================================

class TestBuildQAContext:
    """Test QA context building."""
    
    @pytest.fixture
    def sample_requirements(self):
        """Create sample requirements."""
        return DraftRequirements(
            requirements=[
                DraftRequirement(
                    id="REQ-001",
                    description="Must include position title",
                    element_name="introduction",
                    check_type="keyword",
                    keywords=["position", "title"],
                    is_critical=True,
                ),
                DraftRequirement(
                    id="REQ-002",
                    description="Should reference organization",
                    element_name="introduction",
                    check_type="semantic",
                    is_critical=False,
                ),
            ]
        )
    
    def test_basic_context(self, sample_requirements):
        """Build basic QA context."""
        context = _build_qa_context(
            section_name="introduction",
            section_display_name="Introduction",
            draft_content="This is the introduction section.",
            requirements=sample_requirements,
        )
        
        assert context["section_name"] == "introduction"
        assert context["section_display_name"] == "Introduction"
        assert context["draft_content"] == "This is the introduction section."
        assert len(context["requirements"]) == 2
    
    def test_context_has_requirement_details(self, sample_requirements):
        """Context includes requirement details."""
        context = _build_qa_context(
            section_name="introduction",
            section_display_name="Introduction",
            draft_content="Test content",
            requirements=sample_requirements,
        )
        
        req = context["requirements"][0]
        assert req["id"] == "REQ-001"
        assert req["is_critical"] is True
        assert "position" in req["keywords"]


class TestConvertSchemaToModel:
    """Test schema to model conversion."""
    
    def test_basic_conversion(self):
        """Convert basic schema to model."""
        schema = QAReviewSchema(
            overall_passes=True,
            overall_confidence=0.9,
            overall_feedback="Looks good",
            check_results=[
                QACheckResultSchema(
                    requirement_id="REQ-001",
                    passed=True,
                    confidence=0.95,
                    explanation="Requirement met",
                )
            ],
            needs_rewrite=False,
            suggested_revisions=[],
        )
        
        model = _convert_schema_to_model(schema)
        
        assert isinstance(model, QAReview)
        assert model.passes is True
        assert model.overall_feedback == "Looks good"
        assert len(model.check_results) == 1
        assert model.check_results[0].requirement_id == "REQ-001"
    
    def test_conversion_with_failures(self):
        """Convert schema with failed checks."""
        schema = QAReviewSchema(
            overall_passes=False,
            overall_confidence=0.6,
            overall_feedback="Needs improvement",
            check_results=[
                QACheckResultSchema(
                    requirement_id="REQ-001",
                    passed=False,
                    confidence=0.4,
                    explanation="Missing key content",
                    severity="critical",
                    suggestion="Add position title",
                )
            ],
            needs_rewrite=True,
            suggested_revisions=["Add more detail"],
        )
        
        model = _convert_schema_to_model(schema)
        
        assert model.passes is False
        assert model.needs_rewrite is True
        assert model.check_results[0].severity == "critical"
        assert model.check_results[0].suggestion == "Add position title"


# =============================================================================
# TOOL SCHEMA TESTS (no LLM needed)
# =============================================================================

class TestToolSchemas:
    """Test tool schemas are valid for LLM consumption."""
    
    def test_qa_tools_list(self):
        """Verify QA_TOOLS contains expected tools."""
        tool_names = [t.name for t in QA_TOOLS]
        assert "qa_review_section" in tool_names
        assert "check_qa_status" in tool_names
        assert "request_qa_rewrite" in tool_names
        assert "request_section_approval" in tool_names
        assert "get_qa_thresholds" in tool_names
    
    def test_qa_review_section_schema(self):
        """Verify qa_review_section has proper schema."""
        tool = next(t for t in QA_TOOLS if t.name == "qa_review_section")
        schema = tool.args_schema.model_json_schema()
        
        assert "section_name" in schema["properties"]
        assert "draft_content" in schema["properties"]
        assert "requirements_dict" in schema["properties"]
    
    def test_request_section_approval_schema(self):
        """Verify request_section_approval has proper schema."""
        tool = next(t for t in QA_TOOLS if t.name == "request_section_approval")
        schema = tool.args_schema.model_json_schema()
        
        assert "section_name" in schema["properties"]
        assert "section_content" in schema["properties"]
        assert "qa_passed" in schema["properties"]


# =============================================================================
# TOOL FUNCTION TESTS (no LLM for simple tools)
# =============================================================================

class TestGetQAThresholds:
    """Test get_qa_thresholds tool."""
    
    def test_returns_thresholds(self):
        """Tool returns threshold info."""
        result = get_qa_thresholds.invoke({})
        
        assert "QA Thresholds" in result
        assert "80%" in result  # Pass threshold
        assert "50%" in result  # Rewrite threshold
        assert "1" in result  # Max rewrites


class TestCheckQAStatus:
    """Test check_qa_status tool."""
    
    def test_empty_elements(self):
        """Handle empty elements list."""
        result = check_qa_status.invoke({"draft_elements_list": []})
        assert "No draft elements to review" in result
    
    def test_with_mixed_status(self):
        """Status with mixed QA results."""
        elements = [
            DraftElement(name="intro", display_name="Introduction", status="approved").model_dump(),
            DraftElement(name="bg", display_name="Background", status="qa_passed").model_dump(),
            DraftElement(name="duties", display_name="Duties", status="needs_revision", revision_count=1).model_dump(),
            DraftElement(name="factor1", display_name="Factor 1", status="drafted", content="Draft content").model_dump(),
        ]
        
        result = check_qa_status.invoke({"draft_elements_list": elements})
        
        assert "Approved" in result
        assert "Introduction" in result
        assert "Passed QA" in result
        assert "Background" in result
        assert "Failed QA" in result
        assert "Duties" in result
    
    def test_shows_rewrite_attempt(self):
        """Shows rewrite attempt count."""
        elements = [
            DraftElement(name="intro", display_name="Introduction", status="needs_revision", revision_count=1).model_dump(),
        ]
        
        result = check_qa_status.invoke({"draft_elements_list": elements})
        
        assert "attempt" in result.lower()


class TestRequestQARewrite:
    """Test request_qa_rewrite tool."""
    
    def test_authorize_rewrite(self):
        """Authorize rewrite within limits."""
        result = request_qa_rewrite.invoke({
            "section_name": "introduction",
            "qa_feedback": "Missing complexity indicators",
            "qa_failures": ["REQ-001", "REQ-002"],
            "revision_count": 0,
        })
        
        assert "Rewrite Authorized" in result
        assert "introduction" in result
        assert "Missing complexity indicators" in result
        assert "REQ-001" in result
    
    def test_limit_reached(self):
        """Block rewrite when limit reached."""
        result = request_qa_rewrite.invoke({
            "section_name": "introduction",
            "qa_feedback": "Still needs work",
            "qa_failures": ["REQ-001"],
            "revision_count": MAX_REWRITES,
        })
        
        assert "Rewrite Limit Reached" in result
        assert "request_section_approval" in result


class TestRequestSectionApproval:
    """Test request_section_approval tool."""
    
    def test_passed_qa(self):
        """Request approval for section that passed QA."""
        result = request_section_approval.invoke({
            "section_name": "introduction",
            "section_content": "This is the introduction content.",
            "qa_passed": True,
            "qa_confidence": 0.9,
        })
        
        assert "Passed QA" in result
        assert "introduction" in result
        assert "90%" in result
        assert "approve" in result.lower()
    
    def test_failed_qa(self):
        """Request approval for section that failed QA."""
        result = request_section_approval.invoke({
            "section_name": "introduction",
            "section_content": "This is the introduction content.",
            "qa_passed": False,
            "qa_confidence": 0.6,
            "qa_notes": ["Missing org context", "Too brief"],
        })
        
        assert "human review" in result.lower()
        assert "Missing org context" in result
        assert "Too brief" in result
    
    def test_includes_content(self):
        """Approval request includes section content."""
        content = "The position is located in the IT department..."
        result = request_section_approval.invoke({
            "section_name": "introduction",
            "section_content": content,
            "qa_passed": True,
        })
        
        assert content in result


# =============================================================================
# QA REVIEW TOOL TESTS (error cases - no LLM)
# =============================================================================

class TestQAReviewSectionErrors:
    """Test qa_review_section error handling."""
    
    def test_empty_content_error(self):
        """Return error for empty content."""
        result = qa_review_section.invoke({
            "section_name": "introduction",
            "draft_content": "",
            "requirements_dict": {},
        })
        
        assert "Error" in result
        assert "No draft content" in result
    
    def test_empty_requirements_auto_pass(self):
        """Empty requirements dict leads to auto-pass."""
        result = qa_review_section.invoke({
            "section_name": "introduction",
            "draft_content": "Some test content here.",
            "requirements_dict": {},  # Empty but valid dict
        })
        
        # Should pass QA when no requirements defined
        # (the QA logic says no reqs = auto-pass)
        assert "Error" not in result or "No specific requirements" in result


# =============================================================================
# LLM INTEGRATION TESTS (marked for selective execution)
# =============================================================================

@pytest.mark.llm
@pytest.mark.llm_integration
class TestQAReviewSectionLLM:
    """Integration tests for qa_review_section with real LLM."""
    
    @pytest.fixture
    def sample_requirements_dict(self):
        """Create sample requirements dict."""
        return DraftRequirements(
            requirements=[
                DraftRequirement(
                    id="REQ-001",
                    description="Must include position title",
                    element_name="introduction",
                    check_type="keyword",
                    keywords=["IT Specialist"],
                    is_critical=True,
                ),
                DraftRequirement(
                    id="REQ-002",
                    description="Should reference organization",
                    element_name="introduction",
                    check_type="semantic",
                    is_critical=True,
                ),
            ]
        ).model_dump()
    
    def test_review_passing_content(self, sample_requirements_dict):
        """Review content that should pass."""
        content = """
        This position is an IT Specialist located in the Internal Revenue Service (IRS),
        Information Technology organization. The incumbent serves as a senior software
        developer responsible for designing and implementing critical tax processing systems.
        """
        
        result = qa_review_section.invoke({
            "section_name": "introduction",
            "draft_content": content,
            "requirements_dict": sample_requirements_dict,
        })
        
        assert "QA Review" in result
        assert "Error" not in result
        # Should have confidence info
        assert "%" in result
    
    def test_review_failing_content(self, sample_requirements_dict):
        """Review content that should fail."""
        content = "This is a brief description."  # Missing required elements
        
        result = qa_review_section.invoke({
            "section_name": "introduction",
            "draft_content": content,
            "requirements_dict": sample_requirements_dict,
        })
        
        assert "QA Review" in result
        # Low content should trigger feedback
        assert "%" in result
    
    def test_review_with_no_requirements(self):
        """Review with no requirements (auto-pass)."""
        result = qa_review_section.invoke({
            "section_name": "introduction",
            "draft_content": "Some content here.",
            "requirements_dict": DraftRequirements().model_dump(),
        })
        
        # Should pass when no requirements
        assert "PASSED" in result or "No specific requirements" in result


# =============================================================================
# FULL WORKFLOW TESTS
# =============================================================================

class TestQAWorkflow:
    """Test typical QA workflow sequences."""
    
    def test_status_then_rewrite_flow(self):
        """Test checking status then requesting rewrite."""
        elements = [
            DraftElement(
                name="introduction",
                display_name="Introduction",
                status="needs_revision",
                revision_count=0,
                content="Brief intro",
            ).model_dump(),
        ]
        
        # Check status
        status = check_qa_status.invoke({"draft_elements_list": elements})
        assert "Failed QA" in status
        
        # Request rewrite
        rewrite = request_qa_rewrite.invoke({
            "section_name": "introduction",
            "qa_feedback": "Too brief",
            "qa_failures": ["REQ-001"],
            "revision_count": 0,
        })
        assert "Rewrite Authorized" in rewrite
    
    def test_approval_after_qa_pass(self):
        """Test approval request after QA passes."""
        content = "This is a well-written introduction section."
        
        # Request approval
        approval = request_section_approval.invoke({
            "section_name": "introduction",
            "section_content": content,
            "qa_passed": True,
            "qa_confidence": 0.85,
        })
        
        assert "Passed QA" in approval
        assert "approve" in approval.lower()
        assert content in approval
