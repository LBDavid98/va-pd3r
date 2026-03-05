"""Constants and configuration for PD3r interview flow.

This module re-exports field configuration from the intake_fields registry
and provides backwards-compatible access patterns.
"""

import logging
import os
from pathlib import Path
from typing import Any

from src.config.intake_fields import (
    BASE_INTAKE_SEQUENCE,
    INTAKE_FIELDS,
    JOB_SERIES,
    SUPERVISORY_ADDITIONAL,
    IntakeField,
    get_intake_sequence,
)

# Required fields that must be collected for every position description
REQUIRED_FIELDS: list[str] = [
    name for name, field in INTAKE_FIELDS.items() if field.required
]

# Conditional fields - maps trigger field -> condition -> list of fields to require
CONDITIONAL_FIELDS: dict[str, dict[str, list[str]]] = {}
for name, field in INTAKE_FIELDS.items():
    if field.conditional:
        trigger = field.conditional.depends_on
        value = str(field.conditional.value)
        if trigger not in CONDITIONAL_FIELDS:
            CONDITIONAL_FIELDS[trigger] = {}
        if value not in CONDITIONAL_FIELDS[trigger]:
            CONDITIONAL_FIELDS[trigger][value] = []
        CONDITIONAL_FIELDS[trigger][value].append(name)

# Human-friendly prompts for each interview field
FIELD_PROMPTS: dict[str, str] = {name: field.prompt for name, field in INTAKE_FIELDS.items()}

# Field configuration for validation and extraction hints (backwards compatible)
FIELD_CONFIG: dict[str, dict[str, Any]] = {
    name: {
        "type": field.field_type,
        "validation": field.validation,
        "extraction_hint": field.user_guidance or "",
    }
    for name, field in INTAKE_FIELDS.items()
}

# Full field definitions with all metadata for templates
# Converts Pydantic models to dicts for Jinja template access
FIELD_DEFINITIONS: dict[str, dict[str, Any]] = {
    name: field.model_dump() for name, field in INTAKE_FIELDS.items()
}

# Common OPM series codes for reference
COMMON_SERIES: dict[str, str] = {code: entry.title for code, entry in JOB_SERIES.items()}

# =============================================================================
# Testing Phase Controls (see ADR-004)
# =============================================================================
# These flags allow selective testing of specific workflow phases.
# Set via environment variables for development/testing.

logger = logging.getLogger(__name__)

# STOP_AT: Stop execution at a specific phase and route to END
# Valid values: "interview", "requirements", "drafting", "review", None (disabled)
_stop_at_raw = os.environ.get("PD3R_STOP_AT", "").strip().lower()
STOP_AT: str | None = _stop_at_raw if _stop_at_raw in ("interview", "requirements", "drafting", "review") else None

# SKIP_QA: Skip QA review loop during drafting phase
SKIP_QA: bool = os.environ.get("PD3R_SKIP_QA", "").lower() in ("true", "1", "yes")

# TRACING: Enable local tracing to output/logs/
TRACING: bool = os.environ.get("PD3R_TRACING", "").lower() in ("true", "1", "yes")

# MAX_DRAFTS: Limit number of draft elements (0 = no limit)
# Can be overridden via PD3R_MAX_DRAFTS env var, default from pyproject.toml
def _get_max_drafts_default() -> int:
    """Read max_drafts from pyproject.toml [tool.pd3r] section."""
    try:
        import tomllib
        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        if pyproject_path.exists():
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
            return data.get("tool", {}).get("pd3r", {}).get("max_drafts", 0)
    except Exception:
        pass
    return 0

_max_drafts_env = os.environ.get("PD3R_MAX_DRAFTS", "").strip()
MAX_DRAFTS: int = int(_max_drafts_env) if _max_drafts_env.isdigit() else _get_max_drafts_default()

# Log warnings when testing controls are enabled
if STOP_AT:
    logger.warning(f"⚠️  PD3R_STOP_AT={STOP_AT} - Workflow will stop after {STOP_AT} phase")
if SKIP_QA:
    logger.warning("⚠️  PD3R_SKIP_QA=true - QA review will be skipped during drafting")
if TRACING:
    logger.info("📊 PD3R_TRACING=true - Traces will be written to output/logs/")
if MAX_DRAFTS > 0:
    logger.warning(f"⚠️  PD3R_MAX_DRAFTS={MAX_DRAFTS} - Only {MAX_DRAFTS} element(s) will be drafted")

# Re-export for convenience
__all__ = [
    "REQUIRED_FIELDS",
    "CONDITIONAL_FIELDS",
    "FIELD_PROMPTS",
    "TRACING",
    "FIELD_CONFIG",
    "FIELD_DEFINITIONS",
    "COMMON_SERIES",
    "INTAKE_FIELDS",
    "BASE_INTAKE_SEQUENCE",
    "SUPERVISORY_ADDITIONAL",
    "get_intake_sequence",
    "IntakeField",
    "STOP_AT",
    "SKIP_QA",
    "MAX_DRAFTS",
]
