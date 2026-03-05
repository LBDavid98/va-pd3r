"""Field validation utilities for interview data."""

import re
from typing import Any


# Validation error messages
VALIDATION_ERRORS = {
    "series_invalid": "Please enter a valid 4-digit series code (e.g., 2210, 0343).",
    "grade_invalid": "Please enter a valid GS grade (1-15).",
    "organization_empty": "Please provide at least one organization level.",
    "duties_incomplete": "Please provide duty statements with percentage allocations that sum to 100%.",
    "percentage_invalid": "Percentages must be between 0 and 100.",
}


def validate_series(value: str) -> tuple[bool, str | None]:
    """
    Validate an OPM series code.

    Series codes are 4-digit numbers like "2210" or "0343".

    Args:
        value: The series code to validate

    Returns:
        Tuple of (is_valid, error_message or None)
    """
    if not value:
        return False, VALIDATION_ERRORS["series_invalid"]

    # Strip whitespace and any leading zeros formatting
    cleaned = value.strip()

    # Check if it's a 4-digit number (can have leading zeros)
    if re.match(r"^\d{4}$", cleaned):
        return True, None

    # Also accept series without leading zeros (e.g., "343" for "0343")
    if re.match(r"^\d{1,4}$", cleaned):
        return True, None

    return False, VALIDATION_ERRORS["series_invalid"]


def validate_grade(value: str) -> tuple[bool, str | None]:
    """
    Validate a GS grade level.

    Valid grades are GS-1 through GS-15.

    Args:
        value: The grade to validate (e.g., "13", "GS-13", "GS13", "9")

    Returns:
        Tuple of (is_valid, error_message or None)
    """
    if not value:
        return False, VALIDATION_ERRORS["grade_invalid"]

    cleaned = value.strip().upper()

    # Extract numeric grade
    match = re.search(r"(\d{1,2})", cleaned)
    if not match:
        return False, VALIDATION_ERRORS["grade_invalid"]

    grade_num = int(match.group(1))

    # Valid GS grades are 1-15
    if 1 <= grade_num <= 15:
        return True, None

    return False, VALIDATION_ERRORS["grade_invalid"]


def parse_grade(value: str) -> str | None:
    """
    Parse a grade value into standardized format.

    Args:
        value: Raw grade input (e.g., "13", "GS-13", "Thirteen", "9", "Nine")

    Returns:
        Standardized grade string (e.g., "GS-13") or None if invalid
    """
    if not value:
        return None

    cleaned = value.strip().upper()

    # Handle word forms for all grades 1-15
    word_to_num = {
        "ONE": "1",
        "TWO": "2",
        "THREE": "3",
        "FOUR": "4",
        "FIVE": "5",
        "SIX": "6",
        "SEVEN": "7",
        "EIGHT": "8",
        "NINE": "9",
        "TEN": "10",
        "ELEVEN": "11",
        "TWELVE": "12",
        "THIRTEEN": "13",
        "FOURTEEN": "14",
        "FIFTEEN": "15",
    }

    for word, num in word_to_num.items():
        if word in cleaned:
            return f"GS-{num}"

    # Extract numeric grade
    match = re.search(r"(\d{1,2})", cleaned)
    if match:
        grade_num = int(match.group(1))
        if 1 <= grade_num <= 15:
            return f"GS-{grade_num}"

    return None


def validate_organization(value: list[str]) -> tuple[bool, str | None]:
    """
    Validate organization hierarchy.

    Must have at least one level (agency).

    Args:
        value: List of organization levels

    Returns:
        Tuple of (is_valid, error_message or None)
    """
    if not value or len(value) == 0:
        return False, VALIDATION_ERRORS["organization_empty"]

    # Check that entries are non-empty strings
    if all(isinstance(v, str) and v.strip() for v in value):
        return True, None

    return False, VALIDATION_ERRORS["organization_empty"]


def parse_organization(value: str) -> list[str]:
    """
    Parse organization string into hierarchy list.

    Handles various separators: comma, >, /, semicolon.

    Args:
        value: Raw organization string

    Returns:
        List of organization levels from largest to smallest
    """
    if not value:
        return []

    # Try different separators
    separators = [",", ">", "/", ";"]

    for sep in separators:
        if sep in value:
            parts = [p.strip() for p in value.split(sep) if p.strip()]
            if len(parts) > 1:
                return parts

    # Single value, return as list
    return [value.strip()] if value.strip() else []


def validate_duty_percentages(duties: dict[str, Any]) -> tuple[bool, str | None]:
    """
    Validate that duty percentages sum to approximately 100%.

    Args:
        duties: Dict mapping duty names to percentages

    Returns:
        Tuple of (is_valid, error_message or None)
    """
    if not duties:
        return False, VALIDATION_ERRORS["duties_incomplete"]

    total = 0
    for duty_name, percentage in duties.items():
        # Handle string percentages like "40%" or "40"
        if isinstance(percentage, str):
            match = re.search(r"(\d+)", percentage)
            if match:
                pct = int(match.group(1))
            else:
                return False, VALIDATION_ERRORS["percentage_invalid"]
        else:
            pct = int(percentage)

        if pct < 0 or pct > 100:
            return False, VALIDATION_ERRORS["percentage_invalid"]

        total += pct

    # Allow some tolerance (95-105%)
    if 95 <= total <= 105:
        return True, None

    return False, VALIDATION_ERRORS["duties_incomplete"]


def parse_duties(value: str) -> dict[str, int]:
    """
    Parse duty statements with percentages.

    Handles formats like:
    - "Lead projects 40%; Analyze data 30%; Report 30%"
    - "Lead projects: 40%, Analyze data: 30%"

    Args:
        value: Raw duties string

    Returns:
        Dict mapping duty names to percentages
    """
    if not value:
        return {}

    result = {}

    # Split by semicolon or newline
    parts = re.split(r"[;\n]", value)

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Try to extract percentage
        match = re.search(r"(.+?)\s*[:,-]?\s*(\d+)\s*%?$", part)
        if match:
            duty_name = match.group(1).strip()
            percentage = int(match.group(2))
            result[duty_name] = percentage
        else:
            # No percentage found, add with 0
            result[part] = 0

    return result
