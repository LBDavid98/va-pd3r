"""FES Factor configuration and lookup utilities.

Loads FES factor levels and grade cutoffs from JSON configuration files
and provides lookup functions for grade evaluation.
"""

import json
from pathlib import Path
from typing import Any, Union

from src.models.fes import FESEvaluation, FESFactorLevel, GradeCutoff

# Path to business rules JSON files
BUSINESS_RULES_DIR = Path(__file__).parent.parent.parent / "docs" / "business_rules"

# Load FES factor levels from JSON
_fes_factor_levels_path = BUSINESS_RULES_DIR / "fes_factor_levels.json"
with open(_fes_factor_levels_path) as f:
    _raw_fes_data = json.load(f)
    FES_FACTOR_LEVELS: dict[str, dict] = _raw_fes_data.get("fes_factorLevels", {})

# Load grade cutoffs from JSON
_grade_cutoffs_path = BUSINESS_RULES_DIR / "grade_cutoff_scores.json"
with open(_grade_cutoffs_path) as f:
    _raw_cutoffs = json.load(f)

# Build GRADE_CUTOFFS list from raw data
GRADE_CUTOFFS: list[GradeCutoff] = []
for cutoff_data in _raw_cutoffs:
    if "factors" in cutoff_data:  # Skip entries without factor data
        GRADE_CUTOFFS.append(
            GradeCutoff(
                grade=cutoff_data["GS_Grade"],
                min_points=cutoff_data["Minimum"],
                max_points=cutoff_data.get("Maximum"),
                factors=cutoff_data.get("factors", {}),
            )
        )

# Build lookup dict by grade
GRADE_CUTOFFS_BY_GRADE: dict[int, GradeCutoff] = {gc.grade: gc for gc in GRADE_CUTOFFS}

# Factor names for display
FACTOR_NAMES: dict[int, str] = {
    1: "Knowledge Required by the Position",
    2: "Supervisory Controls",
    3: "Guidelines",
    4: "Complexity",
    5: "Scope and Effect",
    6: "Personal Contacts",
    7: "Purpose of Contacts",
    8: "Physical Demands",
    9: "Work Environment",
}

# Point values for each factor level (from OPM FES standards)
FACTOR_POINTS: dict[int, dict[Union[int, str], int]] = {
    1: {1: 50, 2: 200, 3: 350, 4: 550, 5: 750, 6: 950, 7: 1250, 8: 1550},
    2: {1: 25, 2: 125, 3: 275, 4: 450, 5: 650},
    3: {1: 25, 2: 125, 3: 275, 4: 450, 5: 650},
    4: {1: 25, 2: 75, 3: 150, 4: 225, 5: 325, 6: 450},
    5: {1: 25, 2: 75, 3: 150, 4: 225, 5: 325, 6: 450},
    6: {1: 10, 2: 25, 3: 60, 4: 110},
    7: {"a": 20, "b": 50, "c": 120, "d": 200},
    8: {1: 5, 2: 20},
    9: {1: 5, 2: 20},
}


def get_grade_cutoff(grade: int) -> GradeCutoff | None:
    """
    Get grade cutoff information for a specific GS grade.

    Args:
        grade: GS grade number (e.g., 13)

    Returns:
        GradeCutoff model or None if not found
    """
    return GRADE_CUTOFFS_BY_GRADE.get(grade)


def get_factor_level_for_grade(
    grade: int, factor_num: int, use_max: bool = False
) -> Union[int, str] | None:
    """
    Get the target factor level for a given grade.

    Args:
        grade: GS grade number
        factor_num: Factor number (1-9)
        use_max: If True, return max level; otherwise return typical/min

    Returns:
        Level number/code or None if not found
    """
    cutoff = get_grade_cutoff(grade)
    if cutoff is None:
        return None

    score, _ = cutoff.get_factor_level(factor_num, use_max=use_max)
    return score if score != 0 else None


def _get_level_code(factor_num: int, level: Union[int, str]) -> str:
    """
    Build the level code string for a factor level.
    
    Examples:
        - Factor 1, Level 3 -> "1-3"
        - Factor 7, Level "b" -> "b"
        - Factor 8, Level 1 -> "8-1"
    """
    if factor_num in (6, 7, 8, 9):
        if factor_num == 7:
            return str(level)  # Just "a", "b", "c", "d"
        elif factor_num in (8, 9):
            return f"{factor_num}-{level}"  # "8-1", "9-2"
        else:  # Factor 6
            return str(level)  # Just "1", "2", "3", "4"
    else:
        return f"{factor_num}-{level}"  # "1-3", "2-4", etc.


def _get_level_unique_statements(
    factor_num: int, level: Union[int, str], statement_type: str = "does"
) -> list[str]:
    """
    Get ONLY the unique statements for a specific level (no recursion).
    
    This returns the statements defined at this level, excluding the
    <REF_PRIOR_LEVEL_DUTIES> marker.
    
    Args:
        factor_num: Factor number (1-9)
        level: Level within the factor
        statement_type: "does" for positive statements, "does_not" for exclusions
    
    Returns:
        List of unique statements for this level only
    """
    factor_key = str(factor_num)
    if factor_key not in FES_FACTOR_LEVELS:
        return []
    
    factor_data = FES_FACTOR_LEVELS[factor_key]
    levels_data = factor_data.get("levels", {})
    level_code = _get_level_code(factor_num, level)
    
    if level_code not in levels_data:
        return []
    
    level_data = levels_data[level_code]
    statements = level_data.get(statement_type, [])
    
    # Filter out the reference marker
    return [s for s in statements if s != "<REF_PRIOR_LEVEL_DUTIES>"]


def _expand_does_statements(
    factor_num: int, target_level: Union[int, str], statement_type: str = "does"
) -> list[str]:
    """
    Get statements for a factor level, expanding <REF_PRIOR_LEVEL_DUTIES>.

    IMPORTANT: Per HR guidance, the reference marker means "include the IMMEDIATE
    prior level only" - NOT recursive. For example:
    - Level 1-8 with <REF_PRIOR_LEVEL_DUTIES> includes 1-7's unique statements
    - Level 1-7's reference to 1-6 does NOT propagate up to 1-8
    
    This is a SINGLE LEVEL PRIOR reference, not cumulative.

    Args:
        factor_num: Factor number (1-9)
        target_level: Target level within the factor
        statement_type: "does" for positive statements, "does_not" for exclusions

    Returns:
        List of statements (this level's unique + prior level's unique if referenced)
    """
    factor_key = str(factor_num)
    if factor_key not in FES_FACTOR_LEVELS:
        return []

    factor_data = FES_FACTOR_LEVELS[factor_key]
    levels_data = factor_data.get("levels", {})
    level_code = _get_level_code(factor_num, target_level)

    if level_code not in levels_data:
        return []

    level_data = levels_data[level_code]
    statements = level_data.get(statement_type, [])

    result = []
    for statement in statements:
        if statement == "<REF_PRIOR_LEVEL_DUTIES>":
            # Include ONLY the immediate prior level's unique statements (not recursive)
            prior_level = _get_prior_level(factor_num, target_level)
            if prior_level is not None:
                # Get prior level's unique statements only - NO further recursion
                result.extend(_get_level_unique_statements(factor_num, prior_level, statement_type))
        else:
            result.append(statement)

    return result


def _get_prior_level(factor_num: int, current_level: Union[int, str]) -> Union[int, str] | None:
    """Get the previous level for a factor."""
    if factor_num == 7:
        # Factor 7 uses letters: a, b, c, d
        level_sequence = ["a", "b", "c", "d"]
        try:
            idx = level_sequence.index(str(current_level))
            return level_sequence[idx - 1] if idx > 0 else None
        except ValueError:
            return None
    else:
        # Numeric levels
        try:
            level_int = int(current_level)
            return level_int - 1 if level_int > 1 else None
        except (ValueError, TypeError):
            return None


def get_does_statements(factor_num: int, level: Union[int, str]) -> list[str]:
    """
    Get 'does' statements for a factor level.

    When a level contains <REF_PRIOR_LEVEL_DUTIES>, includes the IMMEDIATE
    prior level's unique statements only (single-level-prior, not recursive).

    Args:
        factor_num: Factor number (1-9)
        level: Level within the factor

    Returns:
        List of 'does' statements for this level
    """
    return _expand_does_statements(factor_num, level, "does")


def get_does_not_statements(factor_num: int, level: Union[int, str]) -> list[str]:
    """
    Get 'does_not' (exclusion) statements for a factor level.
    
    These are things that should NOT appear in the position description
    for this factor level. Useful for QA to catch grade-inappropriate language.
    
    When a level contains <REF_PRIOR_LEVEL_DUTIES>, includes the IMMEDIATE
    prior level's unique exclusion statements only (single-level-prior).

    Args:
        factor_num: Factor number (1-9)
        level: Level within the factor

    Returns:
        List of 'does_not' statements (exclusions) for this level
    """
    return _expand_does_statements(factor_num, level, "does_not")


def get_factor_name(factor_num: int) -> str:
    """Get the human-readable name for a factor."""
    return FACTOR_NAMES.get(factor_num, f"Factor {factor_num}")


def get_factor_points(factor_num: int, level: Union[int, str]) -> int:
    """Get point value for a specific factor level."""
    if factor_num not in FACTOR_POINTS:
        return 0
    level_points = FACTOR_POINTS[factor_num]
    return level_points.get(level, 0)


def build_factor_level(
    factor_num: int, level: Union[int, str], expand_does: bool = True
) -> FESFactorLevel:
    """
    Build a FESFactorLevel model for a specific factor and level.

    Args:
        factor_num: Factor number (1-9)
        level: Level within the factor
        expand_does: If True, expand <REF_PRIOR_LEVEL_DUTIES> markers

    Returns:
        Populated FESFactorLevel model
    """
    # Build level code
    if factor_num == 7:
        level_code = str(level)
    elif factor_num in (8, 9):
        level_code = f"{factor_num}-{level}"
    elif factor_num == 6:
        level_code = str(level)
    else:
        level_code = f"{factor_num}-{level}"

    # Get does statements
    if expand_does:
        does = get_does_statements(factor_num, level)
    else:
        # Get raw does without expansion
        factor_key = str(factor_num)
        if factor_key in FES_FACTOR_LEVELS:
            levels_data = FES_FACTOR_LEVELS[factor_key].get("levels", {})
            does = levels_data.get(level_code, {}).get("does", [])
        else:
            does = []

    return FESFactorLevel(
        factor_num=factor_num,
        factor_name=get_factor_name(factor_num),
        level=level,
        level_code=level_code,
        points=get_factor_points(factor_num, level),
        does=does,
    )


def evaluate_fes_for_grade(grade: int, use_max_levels: bool = False) -> FESEvaluation | None:
    """
    Build a complete FES evaluation for a target grade.

    Looks up the appropriate factor levels for the grade and builds
    a complete FESEvaluation with all 'does' statements expanded.

    Args:
        grade: GS grade number (e.g., 13)
        use_max_levels: If True, use max levels; otherwise use min/typical

    Returns:
        FESEvaluation model or None if grade not found
    """
    cutoff = get_grade_cutoff(grade)
    if cutoff is None:
        return None

    # Build factor levels
    factor_levels = {}
    total_points = 0

    for factor_num in range(1, 10):
        level, points = cutoff.get_factor_level(factor_num, use_max=use_max_levels)
        if level != 0:
            factor_level = build_factor_level(factor_num, level)
            factor_levels[factor_num] = factor_level
            total_points += factor_level.points

    # Build the evaluation
    return FESEvaluation(
        grade=f"GS-{grade}",
        grade_num=grade,
        factor_1_knowledge=factor_levels.get(1),
        factor_2_supervisory_controls=factor_levels.get(2),
        factor_3_guidelines=factor_levels.get(3),
        factor_4_complexity=factor_levels.get(4),
        factor_5_scope_and_effect=factor_levels.get(5),
        factor_6_personal_contacts=factor_levels.get(6),
        factor_7_purpose_of_contacts=factor_levels.get(7),
        factor_8_physical_demands=factor_levels.get(8),
        factor_9_work_environment=factor_levels.get(9),
        total_points=total_points,
    )


def parse_grade_number(grade_str: str) -> int | None:
    """
    Parse a grade string to its numeric value.

    Handles formats like "GS-13", "13", "GS13", etc.

    Args:
        grade_str: Grade string in various formats

    Returns:
        Numeric grade or None if parsing fails
    """
    if not grade_str:
        return None

    # Remove common prefixes
    cleaned = grade_str.upper().replace("GS-", "").replace("GS", "").strip()

    try:
        return int(cleaned)
    except ValueError:
        return None
