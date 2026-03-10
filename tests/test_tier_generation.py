"""Tests for tiered generation system.

Tests the two-tier generation system:
- literal: Fixed text, no LLM call (Factor 8/9)
- llm: Full LLM generation (all narrative sections)
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


class TestGenerationTierRegistry:
    """Test generation tier configuration in SECTION_REGISTRY."""

    def test_all_sections_have_tier(self):
        """Every section should have a generation_tier defined."""
        for section_id, config in SECTION_REGISTRY.items():
            tier = config.get("generation_tier")
            assert tier is not None, f"Section {section_id} missing generation_tier"
            assert tier in ("literal", "llm"), (
                f"Section {section_id} has invalid tier: {tier}"
            )

    def test_literal_tier_sections(self):
        """Factor 8 and 9 should be literal tier."""
        literal_sections = get_sections_by_tier("literal")
        assert "factor_8_physical_demands" in literal_sections
        assert "factor_9_work_environment" in literal_sections
        assert len(literal_sections) == 2

    def test_introduction_is_llm_tier(self):
        """Introduction should be LLM tier, not procedural."""
        assert get_generation_tier("introduction") == "llm"

    def test_background_is_llm_tier(self):
        """Background should be LLM tier, not procedural."""
        assert get_generation_tier("background") == "llm"

    def test_llm_tier_sections(self):
        """Duties, factors 1-7, intro, and background should be LLM tier."""
        llm_sections = get_sections_by_tier("llm")
        assert "introduction" in llm_sections
        assert "background" in llm_sections
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
        assert get_generation_tier("introduction") == "llm"
        assert get_generation_tier("background") == "llm"
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

            elif tier == "llm":
                # LLM sections should have a prompt key
                assert prompt_key is not None, (
                    f"LLM section {section_id} should have a prompt_key"
                )

    def test_all_tiers_covered(self):
        """Verify both tiers have at least one section."""
        assert len(get_sections_by_tier("literal")) > 0
        assert len(get_sections_by_tier("llm")) > 0

    def test_no_orphan_sections(self):
        """Verify no sections are missing from tier classification."""
        literal = set(get_sections_by_tier("literal"))
        llm = set(get_sections_by_tier("llm"))

        all_tiered = literal | llm
        all_sections = set(SECTION_REGISTRY.keys())

        assert all_tiered == all_sections, (
            f"Sections missing tier: {all_sections - all_tiered}"
        )
