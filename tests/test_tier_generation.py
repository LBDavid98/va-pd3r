"""Tests for tiered generation system.

Tests the three-tier generation system:
- literal: Fixed text, no LLM call (Factor 8/9)
- procedural: Template-based generation (intro/background)
- llm: Full LLM generation (duties, factors 1-7)
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add business rules to path
sys.path.insert(0, str(Path(__file__).parent.parent / "docs" / "business_rules"))
from drafting_sections import (
    SECTION_REGISTRY,
    get_generation_tier,
    get_sections_by_tier,
    get_predetermined_narrative,
)

from src.models.interview import InterviewData
from src.utils.procedural_generators import (
    generate_introduction,
    generate_background,
    generate_procedural_content,
    is_procedural_section,
    PROCEDURAL_GENERATORS,
)


class TestGenerationTierRegistry:
    """Test generation tier configuration in SECTION_REGISTRY."""
    
    def test_all_sections_have_tier(self):
        """Every section should have a generation_tier defined."""
        for section_id, config in SECTION_REGISTRY.items():
            tier = config.get("generation_tier")
            assert tier is not None, f"Section {section_id} missing generation_tier"
            assert tier in ("literal", "procedural", "llm"), (
                f"Section {section_id} has invalid tier: {tier}"
            )
    
    def test_literal_tier_sections(self):
        """Factor 8 and 9 should be literal tier."""
        literal_sections = get_sections_by_tier("literal")
        assert "factor_8_physical_demands" in literal_sections
        assert "factor_9_work_environment" in literal_sections
        assert len(literal_sections) == 2
    
    def test_procedural_tier_sections(self):
        """Introduction and background should be procedural tier."""
        procedural_sections = get_sections_by_tier("procedural")
        assert "introduction" in procedural_sections
        assert "background" in procedural_sections
        assert len(procedural_sections) == 2
    
    def test_llm_tier_sections(self):
        """Duties and factors 1-7 should be LLM tier."""
        llm_sections = get_sections_by_tier("llm")
        assert "duties_overview" in llm_sections
        assert "factor_1_knowledge" in llm_sections
        assert "factor_2_supervisory_controls" in llm_sections
        assert "factor_3_guidelines" in llm_sections
        assert "factor_4_complexity" in llm_sections
        assert "factor_5_scope_effect" in llm_sections
        assert "factor_6_7_contacts" in llm_sections
    
    def test_get_generation_tier(self):
        """Test get_generation_tier helper function."""
        assert get_generation_tier("factor_8_physical_demands") == "literal"
        assert get_generation_tier("introduction") == "procedural"
        assert get_generation_tier("duties_overview") == "llm"
        # Unknown section defaults to llm
        assert get_generation_tier("unknown_section") == "llm"
    
    def test_literal_sections_have_no_prompt_key(self):
        """Literal tier sections should have prompt_key=None."""
        for section_id in get_sections_by_tier("literal"):
            config = SECTION_REGISTRY[section_id]
            assert config.get("prompt_key") is None, (
                f"Literal section {section_id} should not have prompt_key"
            )
    
    def test_llm_sections_have_prompt_key(self):
        """LLM tier sections should have a prompt_key."""
        for section_id in get_sections_by_tier("llm"):
            config = SECTION_REGISTRY[section_id]
            assert config.get("prompt_key") is not None, (
                f"LLM section {section_id} should have prompt_key"
            )


class TestLiteralGeneration:
    """Test literal tier generation (Factor 8/9)."""
    
    def test_factor_8_predetermined_narrative(self):
        """Factor 8 should have predetermined narrative."""
        narrative = get_predetermined_narrative("8", "1")
        assert "sedentary" in narrative.lower()
        assert "physical" in narrative.lower()
    
    def test_factor_9_predetermined_narrative(self):
        """Factor 9 should have predetermined narrative."""
        narrative = get_predetermined_narrative("9", "1")
        assert "office" in narrative.lower()
        assert "climate" in narrative.lower() or "travel" in narrative.lower()
    
    def test_unknown_factor_narrative_fallback(self):
        """Unknown factor should return fallback message."""
        narrative = get_predetermined_narrative("99", "1")
        assert "not found" in narrative.lower()


class TestProceduralGeneration:
    """Test procedural tier generation (intro/background)."""
    
    @pytest.fixture
    def sample_interview_data(self):
        """Create sample interview data for testing."""
        data = InterviewData()
        data.position_title.set_value("Senior Data Scientist")
        data.series.set_value("1560")
        data.grade.set_value("GS-13")
        data.organization_hierarchy.set_value([
            "Department of Commerce",
            "Bureau of Economic Analysis",
            "Data Science Division"
        ])
        data.reports_to.set_value("Division Chief")
        data.is_supervisor.set_value(False)
        data.major_duties.set_value([
            "Develop machine learning models",
            "Analyze large datasets",
            "Create data visualizations"
        ])
        return data
    
    @pytest.fixture
    def supervisor_interview_data(self):
        """Create sample interview data for a supervisor."""
        data = InterviewData()
        data.position_title.set_value("Branch Chief")
        data.series.set_value("2210")
        data.grade.set_value("GS-14")
        data.organization_hierarchy.set_value([
            "Department of Defense",
            "IT Division"
        ])
        data.reports_to.set_value("Director")
        data.is_supervisor.set_value(True)
        data.num_supervised.set_value(5)
        data.percent_supervising.set_value(40)
        data.major_duties.set_value([
            "Lead IT modernization projects",
            "Manage development teams"
        ])
        return data
    
    def test_is_procedural_section(self):
        """Test is_procedural_section helper."""
        assert is_procedural_section("introduction") is True
        assert is_procedural_section("background") is True
        assert is_procedural_section("duties_overview") is False
        assert is_procedural_section("factor_1_knowledge") is False
    
    def test_procedural_generators_registered(self):
        """Verify procedural generators are registered."""
        assert "introduction" in PROCEDURAL_GENERATORS
        assert "background" in PROCEDURAL_GENERATORS
    
    def test_generate_introduction_basic(self, sample_interview_data):
        """Test introduction generation with basic data."""
        intro = generate_introduction(sample_interview_data)
        
        assert intro is not None
        assert len(intro) > 50
        assert "Senior Data Scientist" in intro
        assert "1560-13" in intro
        assert "Division Chief" in intro
        assert "Data Science Division" in intro
    
    def test_generate_introduction_supervisor(self, supervisor_interview_data):
        """Test introduction includes supervisory information."""
        intro = generate_introduction(supervisor_interview_data)
        
        assert "supervisor" in intro.lower()
        assert "5 employee" in intro
        assert "40%" in intro
    
    def test_generate_background_basic(self, sample_interview_data):
        """Test background generation with basic data."""
        background = generate_background(sample_interview_data)
        
        assert background is not None
        assert len(background) > 50
        assert "Data Science Division" in background
        assert "1560" in background or "data science" in background.lower()
        assert "GS-13" in background or "senior" in background.lower()
    
    def test_generate_background_series_context(self, sample_interview_data):
        """Test background includes series-specific context."""
        # 1560 series should mention data science
        background = generate_background(sample_interview_data)
        assert "data science" in background.lower() or "statistical" in background.lower()
    
    def test_generate_procedural_content_success(self, sample_interview_data):
        """Test generate_procedural_content for valid sections."""
        intro = generate_procedural_content("introduction", sample_interview_data)
        assert intro is not None
        assert "Senior Data Scientist" in intro
        
        background = generate_procedural_content("background", sample_interview_data)
        assert background is not None
    
    def test_generate_procedural_content_invalid_section(self, sample_interview_data):
        """Test generate_procedural_content returns None for invalid sections."""
        result = generate_procedural_content("duties_overview", sample_interview_data)
        assert result is None
        
        result = generate_procedural_content("factor_1_knowledge", sample_interview_data)
        assert result is None
    
    def test_generate_introduction_minimal_data(self):
        """Test introduction generation with minimal data."""
        data = InterviewData()
        data.position_title.set_value("Analyst")
        
        intro = generate_introduction(data)
        
        assert intro is not None
        assert "Analyst" in intro
        # Should have fallback values
        assert "organization" in intro.lower() or "key" in intro.lower()


class TestProceduralGeneratorEdgeCases:
    """Test edge cases in procedural generators."""
    
    def test_empty_interview_data(self):
        """Test with completely empty interview data."""
        data = InterviewData()
        
        intro = generate_introduction(data)
        assert intro is not None
        assert len(intro) > 0
        
        background = generate_background(data)
        assert background is not None
        assert len(background) > 0
    
    def test_special_characters_in_data(self):
        """Test with special characters in interview data."""
        data = InterviewData()
        data.position_title.set_value("IT Specialist (Data & Analytics)")
        data.organization_hierarchy.set_value(["Dept. of Commerce", "Sub-Agency"])
        data.major_duties.set_value(["Analyze data & create reports"])
        
        intro = generate_introduction(data)
        assert "IT Specialist (Data & Analytics)" in intro
    
    def test_long_organization_hierarchy(self):
        """Test with long organization hierarchy."""
        data = InterviewData()
        data.position_title.set_value("Analyst")
        data.organization_hierarchy.set_value([
            "Department of Commerce",
            "National Institute of Standards and Technology",
            "Information Technology Laboratory",
            "Applied Cybersecurity Division",
            "Security Testing Team"
        ])
        
        intro = generate_introduction(data)
        assert "Security Testing Team" in intro
        
        background = generate_background(data)
        assert "Department of Commerce" in background


class TestTierIntegration:
    """Integration tests for tiered generation."""
    
    def test_tier_consistency(self):
        """Verify tier assignments are internally consistent."""
        for section_id, config in SECTION_REGISTRY.items():
            tier = config.get("generation_tier")
            style = config.get("style")
            prompt_key = config.get("prompt_key")
            
            if tier == "literal":
                # Literal sections should have predetermined_narrative style
                assert style == "predetermined_narrative", (
                    f"Literal section {section_id} should have predetermined_narrative style"
                )
                assert prompt_key is None
            
            elif tier == "procedural":
                # Procedural sections should be in PROCEDURAL_GENERATORS
                assert is_procedural_section(section_id), (
                    f"Procedural section {section_id} should have a generator"
                )
            
            elif tier == "llm":
                # LLM sections should have a prompt key
                assert prompt_key is not None, (
                    f"LLM section {section_id} should have a prompt_key"
                )
    
    def test_all_tiers_covered(self):
        """Verify all three tiers have at least one section."""
        assert len(get_sections_by_tier("literal")) > 0
        assert len(get_sections_by_tier("procedural")) > 0
        assert len(get_sections_by_tier("llm")) > 0
    
    def test_no_orphan_sections(self):
        """Verify no sections are missing from tier classification."""
        literal = set(get_sections_by_tier("literal"))
        procedural = set(get_sections_by_tier("procedural"))
        llm = set(get_sections_by_tier("llm"))
        
        all_tiered = literal | procedural | llm
        all_sections = set(SECTION_REGISTRY.keys())
        
        assert all_tiered == all_sections, (
            f"Sections missing tier: {all_sections - all_tiered}"
        )
