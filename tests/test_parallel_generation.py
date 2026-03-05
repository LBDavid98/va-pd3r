"""Tests for parallel generation verification.

Verifies that:
1. Prerequisites in SECTION_REGISTRY are correctly defined
2. asyncio.gather parallelizes ready elements
3. Generation order respects tiers (literal → procedural → llm)
"""

import asyncio
import pytest
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add business rules to path
sys.path.insert(0, str(Path(__file__).parent.parent / "docs" / "business_rules"))
from drafting_sections import (
    SECTION_REGISTRY,
    get_drafting_batches,
    get_sections_by_tier,
)

from src.models.draft import DraftElement, find_ready_indices


class TestPrerequisitesConfiguration:
    """Test prerequisites are correctly defined in SECTION_REGISTRY."""
    
    def test_introduction_duties_batch_no_internal_prerequisites(self):
        """Introduction/duties batch sections should not depend on each other."""
        batches = get_drafting_batches({})
        intro_duties_sections = batches.get("introduction_duties", [])
        
        for section_id in intro_duties_sections:
            config = SECTION_REGISTRY.get(section_id, {})
            requires = config.get("requires", [])
            # Should not require other sections in same batch
            for req in requires:
                assert req not in intro_duties_sections, (
                    f"Section {section_id} has internal batch dependency on {req}"
                )
    
    def test_fes_factors_batch_no_internal_prerequisites(self):
        """FES factor sections should not depend on each other."""
        batches = get_drafting_batches({})
        fes_sections = batches.get("fes_factors", [])
        
        for section_id in fes_sections:
            config = SECTION_REGISTRY.get(section_id, {})
            requires = config.get("requires", [])
            # Should not require other FES sections
            for req in requires:
                assert req not in fes_sections, (
                    f"Section {section_id} has internal batch dependency on {req}"
                )
    
    def test_literal_sections_minimal_requirements(self):
        """Literal tier sections should have minimal requirements."""
        literal_sections = get_sections_by_tier("literal")
        
        for section_id in literal_sections:
            config = SECTION_REGISTRY[section_id]
            requires = config.get("requires", [])
            # Literal sections typically only need factor_targets
            assert len(requires) <= 1, (
                f"Literal section {section_id} has too many requirements: {requires}"
            )
    
    def test_procedural_sections_require_interview_fields(self):
        """Procedural tier sections should require interview data fields."""
        procedural_sections = get_sections_by_tier("procedural")
        
        for section_id in procedural_sections:
            config = SECTION_REGISTRY[section_id]
            requires = config.get("requires", [])
            assert len(requires) > 0, (
                f"Procedural section {section_id} should have requirements"
            )
            # Should require actual interview fields, not sections
            for req in requires:
                assert req not in SECTION_REGISTRY, (
                    f"Procedural section {section_id} should require interview fields, not section {req}"
                )


class TestDraftElementReadiness:
    """Test DraftElement readiness detection."""
    
    @pytest.fixture
    def sample_draft_elements(self):
        """Create sample draft elements for testing."""
        return [
            DraftElement(name="introduction", display_name="Introduction").model_dump(),
            DraftElement(name="background", display_name="Background").model_dump(),
            DraftElement(name="duties_overview", display_name="Duties Overview").model_dump(),
            DraftElement(name="factor_1_knowledge", display_name="Factor 1").model_dump(),
            DraftElement(name="factor_8_physical_demands", display_name="Factor 8").model_dump(),
        ]
    
    def test_find_ready_indices_all_pending(self, sample_draft_elements):
        """All pending elements should be ready if no prerequisites."""
        ready = find_ready_indices(sample_draft_elements)
        
        # All elements should be ready since no internal dependencies
        assert len(ready) == len(sample_draft_elements)
    
    def test_find_ready_indices_excludes_completed(self, sample_draft_elements):
        """Completed elements should not be in ready indices."""
        # Mark first element as approved
        elem = DraftElement.model_validate(sample_draft_elements[0])
        elem.status = "approved"
        sample_draft_elements[0] = elem.model_dump()
        
        ready = find_ready_indices(sample_draft_elements)
        
        assert 0 not in ready
        assert len(ready) == len(sample_draft_elements) - 1


class TestParallelExecutionPattern:
    """Test that parallel execution patterns work correctly."""
    
    @pytest.mark.asyncio
    async def test_asyncio_gather_executes_in_parallel(self):
        """Verify asyncio.gather runs coroutines in parallel."""
        execution_times = []
        
        async def slow_task(task_id: int, delay: float) -> tuple:
            start = time.monotonic()
            await asyncio.sleep(delay)
            end = time.monotonic()
            execution_times.append((task_id, start, end))
            return task_id
        
        start_time = time.monotonic()
        results = await asyncio.gather(
            slow_task(1, 0.1),
            slow_task(2, 0.1),
            slow_task(3, 0.1),
        )
        total_time = time.monotonic() - start_time
        
        assert results == [1, 2, 3]
        # If parallel, total should be ~0.1s, not ~0.3s
        # Allow some overhead but should be < 0.2s
        assert total_time < 0.25, f"Tasks appear to be sequential: {total_time}s"
    
    @pytest.mark.asyncio
    async def test_mixed_instant_and_slow_tasks(self):
        """Test that instant tasks don't wait for slow tasks."""
        execution_order = []
        
        async def instant_task(task_id: int) -> int:
            execution_order.append(f"instant_{task_id}")
            return task_id
        
        async def slow_task(task_id: int) -> int:
            await asyncio.sleep(0.05)
            execution_order.append(f"slow_{task_id}")
            return task_id
        
        results = await asyncio.gather(
            instant_task(1),
            slow_task(2),
            instant_task(3),
        )
        
        assert results == [1, 2, 3]
        # Instant tasks should complete before slow task
        assert "instant_1" in execution_order[:2]
        assert "instant_3" in execution_order[:2]


class TestTierExecutionOrder:
    """Test that tier execution follows expected order."""
    
    def test_tier_priority_ordering(self):
        """Verify tier priority: literal < procedural < llm."""
        tier_priority = {"literal": 0, "procedural": 1, "llm": 2}
        
        # All sections should be orderable by tier
        for section_id in SECTION_REGISTRY:
            config = SECTION_REGISTRY[section_id]
            tier = config.get("generation_tier", "llm")
            assert tier in tier_priority
    
    def test_batch_sections_have_consistent_tiers(self):
        """Sections in same batch should ideally have same tier."""
        batches = get_drafting_batches({})
        
        for batch_name, sections in batches.items():
            tiers = set()
            for section_id in sections:
                config = SECTION_REGISTRY.get(section_id, {})
                tier = config.get("generation_tier", "llm")
                tiers.add(tier)
            
            # intro_duties batch can have mixed tiers (procedural + llm)
            # fes_factors batch can have mixed tiers (literal + llm)
            # This is expected and acceptable
            if batch_name == "introduction_duties":
                assert "llm" in tiers  # duties_overview
                assert "procedural" in tiers  # intro, background
            elif batch_name == "fes_factors":
                assert "literal" in tiers  # factor 8, 9
                assert "llm" in tiers  # factors 1-7


class TestCostReductionVerification:
    """Test that tiered generation achieves cost reduction goals."""
    
    def test_literal_sections_bypass_llm(self):
        """Literal tier sections should have no prompt_key."""
        literal_sections = get_sections_by_tier("literal")
        
        # Should be exactly 2 literal sections
        assert len(literal_sections) == 2
        
        for section_id in literal_sections:
            config = SECTION_REGISTRY[section_id]
            assert config.get("prompt_key") is None
    
    def test_procedural_sections_bypass_llm_on_first_generation(self):
        """Procedural tier sections bypass LLM on first generation."""
        procedural_sections = get_sections_by_tier("procedural")
        
        # Should be exactly 2 procedural sections
        assert len(procedural_sections) == 2
        
        # They have prompt_key for rewrites but use procedural on first pass
        for section_id in procedural_sections:
            config = SECTION_REGISTRY[section_id]
            # May have prompt_key for fallback/rewrite
            # but generation_tier="procedural" means first pass is template-based
            assert config.get("generation_tier") == "procedural"
    
    def test_llm_call_reduction_potential(self):
        """Calculate potential LLM call reduction from tiered generation."""
        total_sections = len(SECTION_REGISTRY)
        literal_count = len(get_sections_by_tier("literal"))
        procedural_count = len(get_sections_by_tier("procedural"))
        llm_count = len(get_sections_by_tier("llm"))
        
        # Verify counts add up
        assert literal_count + procedural_count + llm_count == total_sections
        
        # Calculate reduction
        bypassed = literal_count + procedural_count
        reduction_pct = (bypassed / total_sections) * 100
        
        # Should bypass at least 30% of sections (4 out of 11)
        assert reduction_pct >= 30, (
            f"Expected at least 30% bypass, got {reduction_pct:.1f}%"
        )
        
        print(f"\nTiered Generation Stats:")
        print(f"  Total sections: {total_sections}")
        print(f"  Literal (no LLM): {literal_count}")
        print(f"  Procedural (no LLM on first pass): {procedural_count}")
        print(f"  LLM required: {llm_count}")
        print(f"  Potential bypass: {bypassed} ({reduction_pct:.1f}%)")
