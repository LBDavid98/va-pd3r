"""Unit tests for FES models and configuration."""

import pytest

from src.config.fes_factors import (
    GRADE_CUTOFFS,
    GRADE_CUTOFFS_BY_GRADE,
    FES_FACTOR_LEVELS,
    build_factor_level,
    evaluate_fes_for_grade,
    get_does_statements,
    get_factor_level_for_grade,
    get_factor_name,
    get_factor_points,
    get_grade_cutoff,
    parse_grade_number,
)
from src.models.fes import FESEvaluation, FESFactorLevel, GradeCutoff


class TestFESModels:
    """Tests for FES Pydantic models."""

    def test_fes_factor_level_creation(self):
        """Test creating a FESFactorLevel."""
        level = FESFactorLevel(
            factor_num=1,
            factor_name="Knowledge",
            level=6,
            level_code="1-6",
            points=950,
            does=["Statement 1", "Statement 2"],
        )
        assert level.factor_num == 1
        assert level.factor_name == "Knowledge"
        assert level.level == 6
        assert level.level_code == "1-6"
        assert level.points == 950
        assert len(level.does) == 2

    def test_fes_factor_level_display(self):
        """Test display_level property."""
        level = FESFactorLevel(
            factor_num=2,
            factor_name="Supervisory Controls",
            level=4,
            level_code="2-4",
            points=450,
            does=[],
        )
        assert level.display_level == "Factor 2 Level 2-4"

    def test_fes_evaluation_primary_factors(self):
        """Test FESEvaluation primary_factors property."""
        fes = FESEvaluation(
            grade="GS-13",
            grade_num=13,
            factor_1_knowledge=FESFactorLevel(
                factor_num=1, factor_name="Knowledge", level=8, level_code="1-8", points=1550, does=[]
            ),
            factor_2_supervisory_controls=FESFactorLevel(
                factor_num=2, factor_name="Supervisory Controls", level=4, level_code="2-4", points=450, does=[]
            ),
        )
        primary = fes.primary_factors
        assert len(primary) == 2
        assert primary[0].factor_num == 1
        assert primary[1].factor_num == 2

    def test_fes_evaluation_other_significant_factors(self):
        """Test FESEvaluation other_significant_factors property."""
        fes = FESEvaluation(
            grade="GS-13",
            grade_num=13,
            factor_6_personal_contacts=FESFactorLevel(
                factor_num=6, factor_name="Personal Contacts", level=3, level_code="3", points=60, does=[]
            ),
            factor_8_physical_demands=FESFactorLevel(
                factor_num=8, factor_name="Physical Demands", level=1, level_code="8-1", points=5, does=[]
            ),
        )
        other = fes.other_significant_factors
        assert len(other) == 2
        assert other[0].factor_num == 6
        assert other[1].factor_num == 8

    def test_fes_evaluation_get_factor(self):
        """Test get_factor method."""
        fes = FESEvaluation(
            grade="GS-13",
            grade_num=13,
            factor_3_guidelines=FESFactorLevel(
                factor_num=3, factor_name="Guidelines", level=4, level_code="3-4", points=450, does=[]
            ),
        )
        factor = fes.get_factor(3)
        assert factor is not None
        assert factor.factor_name == "Guidelines"

        missing = fes.get_factor(1)
        assert missing is None

    def test_grade_cutoff_model(self):
        """Test GradeCutoff model."""
        cutoff = GradeCutoff(
            grade=13,
            min_points=3155,
            max_points=3600,
            factors={
                "1": {"min": {"score": 8, "points": 1550}, "max": {"score": 8, "points": 1550}},
            },
        )
        assert cutoff.grade == 13
        assert cutoff.display_range == "3155-3600"

        score, points = cutoff.get_factor_level(1)
        assert score == 8
        assert points == 1550


class TestFESConfiguration:
    """Tests for FES configuration loading and lookup."""

    def test_fes_factor_levels_loaded(self):
        """Test that FES factor levels are loaded from JSON."""
        assert len(FES_FACTOR_LEVELS) > 0
        assert "1" in FES_FACTOR_LEVELS  # Factor 1 exists
        assert "levels" in FES_FACTOR_LEVELS["1"]

    def test_grade_cutoffs_loaded(self):
        """Test that grade cutoffs are loaded."""
        assert len(GRADE_CUTOFFS) > 0
        # Should have entries for common grades
        assert 13 in GRADE_CUTOFFS_BY_GRADE
        assert 14 in GRADE_CUTOFFS_BY_GRADE

    def test_get_grade_cutoff(self):
        """Test get_grade_cutoff function."""
        cutoff = get_grade_cutoff(13)
        assert cutoff is not None
        assert cutoff.grade == 13
        assert cutoff.min_points == 3155

        missing = get_grade_cutoff(99)
        assert missing is None

    def test_get_factor_level_for_grade(self):
        """Test get_factor_level_for_grade function."""
        level = get_factor_level_for_grade(13, 1)
        assert level == 8  # GS-13 requires Factor 1 Level 8

        level_2 = get_factor_level_for_grade(13, 2)
        assert level_2 == 4  # GS-13 requires Factor 2 Level 4

    def test_get_factor_name(self):
        """Test get_factor_name function."""
        assert get_factor_name(1) == "Knowledge Required by the Position"
        assert get_factor_name(2) == "Supervisory Controls"
        assert get_factor_name(5) == "Scope and Effect"

    def test_get_factor_points(self):
        """Test get_factor_points function."""
        assert get_factor_points(1, 8) == 1550
        assert get_factor_points(2, 4) == 450
        assert get_factor_points(7, "c") == 120  # Factor 7 uses letters

    def test_parse_grade_number(self):
        """Test parse_grade_number function."""
        assert parse_grade_number("GS-13") == 13
        assert parse_grade_number("13") == 13
        assert parse_grade_number("GS13") == 13
        assert parse_grade_number("gs-14") == 14
        assert parse_grade_number("invalid") is None
        assert parse_grade_number("") is None


class TestDoesStatementExpansion:
    """Tests for 'does' statement expansion."""

    def test_get_does_statements_basic(self):
        """Test getting does statements for a basic level."""
        does = get_does_statements(1, 1)  # Factor 1, Level 1
        assert len(does) > 0
        assert isinstance(does[0], str)

    def test_get_does_statements_with_expansion(self):
        """Test that REF_PRIOR_LEVEL_DUTIES is expanded."""
        # Level 1-7 should include expanded prior levels
        does = get_does_statements(1, 7)
        assert len(does) > 0
        # Should NOT contain the marker
        assert "<REF_PRIOR_LEVEL_DUTIES>" not in does

    def test_get_does_statements_factor_7(self):
        """Test factor 7 with letter levels."""
        does = get_does_statements(7, "b")
        assert len(does) > 0

    def test_single_level_prior_only(self):
        """Test that <REF_PRIOR_LEVEL_DUTIES> only includes ONE level back, not recursive.
        
        Per HR guidance:
        - Level 1-8 should include 1-7's UNIQUE statements
        - It should NOT recursively include 1-6, 1-5, etc.
        - This prevents bloated factor narratives at senior levels
        
        The marker means "all of the preceding level" = ONE level, not ALL prior levels.
        """
        # Get statements for level 1-7 (the prior level)
        does_7 = get_does_statements(1, 7)
        
        # Get statements for level 1-8 (which has <REF_PRIOR_LEVEL_DUTIES>)
        does_8 = get_does_statements(1, 8)
        
        # Level 1-8 should have its own statements PLUS 1-7's unique statements
        # But NOT a recursive expansion of all levels 1-1 through 1-7
        
        # Key test: Level 1-8 should not have an unreasonable number of statements
        # If it were recursive, it would have 20+ statements
        # With single-level-prior, it should have roughly same count as 1-7 or slightly more
        assert len(does_8) < 15, (
            f"Level 1-8 has {len(does_8)} statements - this suggests recursive expansion. "
            f"Single-level-prior should yield fewer statements."
        )
        
        # The marker should not appear in the final output
        assert "<REF_PRIOR_LEVEL_DUTIES>" not in does_8
        assert "<REF_PRIOR_LEVEL_DUTIES>" not in does_7

    def test_build_factor_level(self):
        """Test build_factor_level function."""
        level = build_factor_level(1, 6)
        assert level.factor_num == 1
        assert level.level == 6
        assert level.level_code == "1-6"
        assert level.points == 950
        assert len(level.does) > 0


class TestFESEvaluation:
    """Tests for complete FES evaluation."""

    def test_evaluate_fes_for_grade_13(self):
        """Test FES evaluation for GS-13."""
        fes = evaluate_fes_for_grade(13)
        assert fes is not None
        assert fes.grade == "GS-13"
        assert fes.grade_num == 13

        # Check primary factors
        assert fes.factor_1_knowledge is not None
        assert fes.factor_1_knowledge.level == 8

        # Check total points
        assert fes.total_points > 0

    def test_evaluate_fes_for_grade_invalid(self):
        """Test FES evaluation for invalid grade."""
        fes = evaluate_fes_for_grade(99)
        assert fes is None

    def test_fes_all_does_statements(self):
        """Test getting all does statements from evaluation."""
        fes = evaluate_fes_for_grade(13)
        all_does = fes.get_all_does_statements()

        assert len(all_does) > 0
        assert 1 in all_does  # Factor 1 should be present
        assert len(all_does[1]) > 0  # Should have does statements
