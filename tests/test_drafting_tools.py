"""Tests for drafting tools.

These tests verify the drafting tool wrappers work correctly.
Per ADR-005, we use real LLM calls where needed (marked with @pytest.mark.llm).
"""

import pytest
from unittest.mock import MagicMock, patch

from src.tools.drafting_tools import (
    DRAFTING_TOOLS,
    _build_draft_context,
    _extract_grade_num,
    _format_org,
    _get_section_config,
    get_section_requirements,
    get_section_status,
    list_available_sections,
    revise_section,
    write_section,
)
from src.models.interview import InterviewData
from src.models.draft import DraftElement
from src.models.fes import FESEvaluation


# =============================================================================
# HELPER FUNCTION TESTS (no LLM needed)
# =============================================================================

class TestExtractGradeNum:
    """Test grade extraction helper."""
    
    def test_extract_gs13(self):
        """Extract from GS-13 format."""
        assert _extract_grade_num("GS-13") == 13
    
    def test_extract_gs_space(self):
        """Extract from GS 13 format."""
        assert _extract_grade_num("GS13") == 13
    
    def test_extract_plain_number(self):
        """Extract from plain number."""
        assert _extract_grade_num("13") == 13
    
    def test_extract_none(self):
        """Handle None input."""
        assert _extract_grade_num(None) == 0
    
    def test_extract_empty(self):
        """Handle empty string."""
        assert _extract_grade_num("") == 0
    
    def test_extract_invalid(self):
        """Handle invalid input."""
        assert _extract_grade_num("invalid") == 0


class TestFormatOrg:
    """Test organization formatting helper."""
    
    def test_format_list(self):
        """Format list of org levels."""
        result = _format_org(["IRS", "IT", "Data Services"])
        assert result == "IRS > IT > Data Services"
    
    def test_format_string(self):
        """Format string org."""
        assert _format_org("IRS") == "IRS"
    
    def test_format_none(self):
        """Handle None."""
        assert _format_org(None) == ""
    
    def test_format_empty_list(self):
        """Handle empty list."""
        assert _format_org([]) == ""


class TestGetSectionConfig:
    """Test section config retrieval."""
    
    def test_valid_section(self):
        """Get config for valid section."""
        config = _get_section_config("introduction")
        assert "description" in config
        assert config.get("style") == "narrative"
    
    def test_factor_section(self):
        """Get config for FES factor section."""
        config = _get_section_config("factor_1_knowledge")
        assert config.get("factor_id") == "1"
    
    def test_invalid_section(self):
        """Get config for invalid section returns empty dict."""
        config = _get_section_config("nonexistent_section")
        assert config == {}


# =============================================================================
# CONTEXT BUILDING TESTS
# =============================================================================

class TestBuildDraftContext:
    """Test draft context building."""
    
    @pytest.fixture
    def sample_interview_data(self):
        """Create sample interview data."""
        data = InterviewData()
        data.position_title.value = "IT Specialist"
        data.series.value = "2210"
        data.grade.value = "GS-13"
        data.organization.value = ["IRS", "IT Services"]
        data.reports_to.value = "Branch Chief"
        data.is_supervisor.value = False
        data.major_duties.value = ["Develop software", "Review code"]
        return data
    
    def test_basic_context(self, sample_interview_data):
        """Build basic context without FES."""
        context = _build_draft_context(
            section_name="introduction",
            interview_data=sample_interview_data,
            fes_evaluation=None,
            requirements=None,
        )
        
        assert context["position_title"] == "IT Specialist"
        assert context["series"] == "2210"
        assert context["grade"] == 13
        assert "IRS" in context["organization"]
        assert context["is_rewrite"] is False
    
    def test_context_with_qa_feedback(self, sample_interview_data):
        """Build context with QA feedback for rewrite."""
        context = _build_draft_context(
            section_name="introduction",
            interview_data=sample_interview_data,
            fes_evaluation=None,
            requirements=None,
            is_rewrite=True,
            qa_feedback="Missing complexity indicators",
            qa_failures=["REQ-001", "REQ-002"],
        )
        
        assert context["is_rewrite"] is True
        assert context["qa_feedback"] == "Missing complexity indicators"
        assert len(context["qa_failures"]) == 2


# =============================================================================
# TOOL SCHEMA TESTS (no LLM needed)
# =============================================================================

class TestToolSchemas:
    """Test tool schemas are valid for LLM consumption."""
    
    def test_drafting_tools_list(self):
        """Verify DRAFTING_TOOLS contains expected tools."""
        tool_names = [t.name for t in DRAFTING_TOOLS]
        assert "write_section" in tool_names
        assert "revise_section" in tool_names
        assert "get_section_status" in tool_names
        assert "list_available_sections" in tool_names
        assert "get_section_requirements" in tool_names
    
    def test_write_section_schema(self):
        """Verify write_section has proper schema."""
        tool = next(t for t in DRAFTING_TOOLS if t.name == "write_section")
        schema = tool.args_schema.model_json_schema()
        
        # Required parameters
        assert "section_name" in schema["properties"]
        assert "interview_data_dict" in schema["properties"]
    
    def test_revise_section_schema(self):
        """Verify revise_section has proper schema."""
        tool = next(t for t in DRAFTING_TOOLS if t.name == "revise_section")
        schema = tool.args_schema.model_json_schema()
        
        assert "section_name" in schema["properties"]
        assert "current_content" in schema["properties"]
        assert "qa_feedback" in schema["properties"]
        assert "qa_failures" in schema["properties"]


# =============================================================================
# TOOL FUNCTION TESTS (no LLM for status/listing tools)
# =============================================================================

class TestListAvailableSections:
    """Test list_available_sections tool."""
    
    def test_returns_sections(self):
        """Tool returns formatted section list."""
        result = list_available_sections.invoke({})
        
        assert "## Available PD Sections" in result
        assert "introduction" in result
        assert "factor_1_knowledge" in result
    
    def test_includes_descriptions(self):
        """Result includes section descriptions."""
        result = list_available_sections.invoke({})
        
        assert "narrative" in result.lower()


class TestGetSectionStatus:
    """Test get_section_status tool."""
    
    def test_empty_elements(self):
        """Handle empty elements list."""
        result = get_section_status.invoke({"draft_elements_list": []})
        assert "No draft elements initialized" in result
    
    def test_with_elements(self):
        """Status with draft elements."""
        elements = [
            DraftElement(name="introduction", display_name="Introduction", status="approved").model_dump(),
            DraftElement(name="background", display_name="Background", status="pending").model_dump(),
            DraftElement(name="factor_1", display_name="Factor 1", status="needs_revision", revision_count=1).model_dump(),
        ]
        
        result = get_section_status.invoke({"draft_elements_list": elements})
        
        assert "Completed" in result
        assert "Introduction" in result
        assert "Pending" in result
        assert "Background" in result
        assert "Needs Revision" in result


class TestGetSectionRequirements:
    """Test get_section_requirements tool."""
    
    def test_valid_section(self):
        """Get requirements for valid section."""
        result = get_section_requirements.invoke({
            "section_name": "introduction",
            "requirements_dict": None,
        })
        
        assert "introduction" in result.lower()
        assert "Required Interview Data" in result
    
    def test_factor_section(self):
        """Get requirements for FES factor section."""
        result = get_section_requirements.invoke({
            "section_name": "factor_1_knowledge",
            "requirements_dict": None,
        })
        
        assert "Factor 1" in result
    
    def test_invalid_section(self):
        """Handle invalid section."""
        result = get_section_requirements.invoke({
            "section_name": "nonexistent",
            "requirements_dict": None,
        })
        
        assert "Error" in result


# =============================================================================
# WRITE/REVISE TOOL TESTS (these need LLM or mocking)
# =============================================================================

class TestWriteSection:
    """Test write_section tool - error cases only (no LLM)."""
    
    def test_invalid_section_returns_error(self):
        """Invalid section name returns error."""
        result = write_section.invoke({
            "section_name": "nonexistent_section",
            "interview_data_dict": {},
        })
        
        assert "Error" in result
        assert "Unknown section" in result


class TestReviseSection:
    """Test revise_section tool."""
    
    def test_invalid_section_returns_error(self):
        """Invalid section name returns error."""
        result = revise_section.invoke({
            "section_name": "nonexistent",
            "current_content": "Some content",
            "qa_feedback": "Needs work",
            "qa_failures": ["REQ-001"],
            "interview_data_dict": {},
        })
        
        assert "Error" in result
        assert "Unknown section" in result


# =============================================================================
# LLM INTEGRATION TESTS (marked for selective execution)
# =============================================================================

@pytest.mark.llm
@pytest.mark.llm_integration
class TestWriteSectionLLM:
    """Integration tests for write_section with real LLM."""
    
    @pytest.fixture
    def sample_interview_dict(self):
        """Create sample interview data dict."""
        data = InterviewData()
        data.position_title.value = "IT Specialist (Applications Software)"
        data.series.value = "2210"
        data.grade.value = "GS-13"
        data.organization.value = ["IRS", "IT Services", "Software Development"]
        data.reports_to.value = "Branch Chief"
        data.is_supervisor.value = False
        data.major_duties.value = [
            "Design and develop software applications",
            "Review code and mentor junior developers",
            "Participate in system architecture decisions",
        ]
        return data.model_dump()
    
    def test_write_introduction(self, sample_interview_dict):
        """Write introduction section with real LLM."""
        result = write_section.invoke({
            "section_name": "introduction",
            "interview_data_dict": sample_interview_dict,
        })
        
        # Should return actual content, not an error
        assert "Error" not in result
        assert len(result) > 100  # Should be substantial content
        # Should reference position info
        assert any(term in result.lower() for term in ["it specialist", "software", "irs"])
    
    def test_write_predetermined_section(self, sample_interview_dict):
        """Write predetermined narrative section (factor 8)."""
        result = write_section.invoke({
            "section_name": "factor_8_physical_demands",
            "interview_data_dict": sample_interview_dict,
        })
        
        # Predetermined sections use fixed content
        assert "sedentary" in result.lower()


@pytest.mark.llm
@pytest.mark.llm_integration
class TestReviseSectionLLM:
    """Integration tests for revise_section with real LLM."""
    
    @pytest.fixture
    def sample_interview_dict(self):
        """Create sample interview data dict."""
        data = InterviewData()
        data.position_title.value = "IT Specialist"
        data.series.value = "2210"
        data.grade.value = "GS-13"
        data.major_duties.value = ["Develop software", "Review code"]
        return data.model_dump()
    
    def test_revise_with_feedback(self, sample_interview_dict):
        """Revise section based on QA feedback."""
        result = revise_section.invoke({
            "section_name": "introduction",
            "current_content": "This is a brief introduction to the position.",
            "qa_feedback": "Introduction is too brief. Add more detail about organizational context.",
            "qa_failures": ["missing_org_context"],
            "interview_data_dict": sample_interview_dict,
        })
        
        # Should return revised content
        assert "Error" not in result
        assert len(result) > 50
