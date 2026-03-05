"""State compaction utilities for PD3r.

This module provides utilities for compacting agent state at phase transitions
to reduce memory usage and prompt token counts while preserving essential data.

ARCHITECTURE DECISION: Dense State / Light Prompts
==================================================
We maintain FULL state for:
- Debugging and tracing
- Export functionality
- User queries about drafts ("why did you change that?")
- Session resume from checkpoints

We COMPACT only:
- Verbose internals that aren't needed for downstream operations
- Transient extraction artifacts
- Intermediate chain-of-thought artifacts

The real optimization happens in `context_builders.py` which selects
minimal context for each LLM prompt while keeping full state available.

PRESERVATION TIERS
==================
State fields are categorized into preservation tiers:

TIER 1 - NEVER COMPACT (Session-Long):
    These fields must remain available until the user quits or starts a new PD:
    - draft_elements[].content (final approved content for export/reference)
    - draft_elements[].status (workflow tracking)
    - draft_elements[].qa_review (most recent QA for user visibility)
    - interview_data (canonical form for export and user queries)
    - fes_evaluation (grade justification)
    - draft_requirements (export metadata)

TIER 2 - COMPACT AFTER ELEMENT APPROVED:
    These fields are needed during drafting but can be summarized after approval:
    - draft_elements[].draft_history → keep count only, drop verbose content
    - draft_elements[].qa_history → keep last entry only
    - draft_elements[].qa_notes → clear after approval

TIER 3 - COMPACT AT PHASE TRANSITIONS:
    Transient fields cleared after use:
    - _field_mappings (cleared after map_answers)
    - pending_question (cleared after answered)
    - last_error (cleared after handled)
    - validation_error (cleared after resolved)

USAGE
=====
State compaction is called at specific phase boundaries:

1. `compact_after_interview()` - Called when interview_complete → requirements
   - Clears extraction artifacts
   - Preserves canonical interview_data

2. `compact_after_element_approved(element_index)` - Called when element approved
   - Compacts draft_history to summary
   - Keeps only latest qa_review

3. `compact_after_export()` - Called when export_complete
   - Clears per-element verbose data
   - Preserves document content and paths

TESTING
=======
All compaction functions have corresponding tests that verify:
- Essential data is NEVER lost
- Compacted data is still usable for its purpose
- State remains valid for LangGraph checkpointing

See: tests/test_state_compaction.py
"""

import logging
from copy import deepcopy
from typing import Any, Optional

from src.models.draft import DraftElement
from src.models.state import AgentState

logger = logging.getLogger(__name__)


# ============================================================================
# TIER DEFINITIONS
# ============================================================================

# Fields that must NEVER be compacted during a session
TIER_1_NEVER_COMPACT = frozenset({
    # Core state for workflow
    "phase",
    "messages",  # Conversation history (managed by LangGraph)
    "should_end",
    "next_prompt",
    
    # Interview data (canonical form)
    "interview_data",
    
    # FES evaluation (grade justification)
    "fes_evaluation",
    
    # Requirements (export metadata)
    "draft_requirements",
    
    # Draft elements (content always preserved - see element-level compaction)
    "draft_elements",
    
    # Write-another flow control
    "wants_another",
    "is_restart",
    "is_resume",
})

# Element fields that must NEVER be compacted
ELEMENT_TIER_1_NEVER_COMPACT = frozenset({
    "name",
    "display_name",
    "content",  # CRITICAL: Final approved content for export
    "status",
    "qa_review",  # Most recent QA for user visibility
    "prerequisites",
})

# Element fields that can be compacted after approval
ELEMENT_TIER_2_COMPACT_AFTER_APPROVAL = frozenset({
    "draft_history",  # Keep summary only
    "qa_history",  # Keep last entry only
    "qa_notes",  # Clear after approval
    "feedback",  # User feedback (incorporated into history)
})

# Transient state fields (cleared at phase transitions)
TIER_3_TRANSIENT = frozenset({
    "_field_mappings",
    "pending_question",
    "last_error",
    "validation_error",
    "current_field",  # Only needed during interview
    "fields_needing_confirmation",  # Only needed during interview
})


# ============================================================================
# COMPACTION FUNCTIONS
# ============================================================================

def compact_after_interview(state: AgentState) -> dict:
    """
    Compact state after interview phase completes.
    
    Called at: interview_complete → requirements transition
    
    Actions:
    - Clears transient extraction fields (_field_mappings)
    - Clears field tracking (current_field, fields_needing_confirmation)
    - Preserves canonical interview_data
    
    Args:
        state: Current agent state
        
    Returns:
        State update dict with cleared transient fields
        
    Note:
        Returns only the fields that should be UPDATED, not a full state copy.
        LangGraph will merge these updates with existing state.
    """
    logger.debug("Compacting state after interview completion")
    
    updates = {
        # Clear transient extraction artifacts
        "_field_mappings": None,
        
        # Clear interview tracking (no longer needed)
        "current_field": None,
        "fields_needing_confirmation": [],
        
        # Clear any pending question
        "pending_question": None,
        
        # Clear validation errors
        "validation_error": None,
    }
    
    logger.info(f"Post-interview compaction cleared {len(updates)} transient fields")
    return updates


def compact_after_element_approved(
    state: AgentState,
    element_index: int,
) -> dict:
    """
    Compact a single draft element after user approval.
    
    Called at: element approved → next_element transition
    
    Actions:
    - Compacts draft_history to summary (keeps attempt count and reasons)
    - Keeps only the latest qa_review (not full history)
    - Clears verbose qa_notes
    - Preserves: content, status, name, qa_review (latest)
    
    Args:
        state: Current agent state
        element_index: Index of the approved element in draft_elements
        
    Returns:
        State update dict with compacted draft_elements
        
    Note:
        This function creates a deep copy of draft_elements to avoid
        mutating state in place (LangGraph best practice).
    """
    draft_elements = state.get("draft_elements", [])
    
    if not draft_elements or element_index >= len(draft_elements):
        logger.warning(f"Invalid element_index {element_index} for compaction")
        return {}
    
    # Deep copy to avoid state mutation
    compacted_elements = deepcopy(draft_elements)
    elem_dict = compacted_elements[element_index]
    elem = DraftElement.model_validate(elem_dict)
    
    if elem.status != "approved":
        logger.debug(f"Element {elem.name} not approved, skipping compaction")
        return {}
    
    logger.debug(f"Compacting approved element: {elem.name}")
    
    # Compact draft_history: keep summary metadata, drop verbose content
    if elem.draft_history:
        compacted_history = _compact_draft_history(elem.draft_history)
        elem_dict["draft_history"] = compacted_history
    
    # Compact qa_history: keep only latest entry
    if elem.qa_history and len(elem.qa_history) > 1:
        elem_dict["qa_history"] = [elem.qa_history[-1]]
    
    # Clear verbose qa_notes (suggestions already incorporated)
    elem_dict["qa_notes"] = []
    
    # Clear feedback (already in history)
    elem_dict["feedback"] = ""
    
    # Clear rewrite tracking (no longer needed)
    elem_dict["rewrite_reason"] = None
    
    compacted_elements[element_index] = elem_dict
    
    logger.info(f"Compacted element {elem.name} (index {element_index})")
    return {"draft_elements": compacted_elements}


def compact_after_export(state: AgentState) -> dict:
    """
    Compact state after document export completes.
    
    Called at: export_complete → write_another OR end transition
    
    Actions:
    - Compacts all element histories (not just approved ones)
    - Clears per-element verbose data
    - Preserves: content, status, qa_review (for reference)
    
    Args:
        state: Current agent state
        
    Returns:
        State update dict with compacted state
        
    Note:
        After export, the document exists as a file. We preserve
        enough state for "write another" flow and debugging.
    """
    logger.debug("Compacting state after export")
    
    draft_elements = state.get("draft_elements", [])
    
    if not draft_elements:
        return {}
    
    # Deep copy to avoid state mutation
    compacted_elements = deepcopy(draft_elements)
    
    for i, elem_dict in enumerate(compacted_elements):
        # Compact draft_history
        if elem_dict.get("draft_history"):
            elem_dict["draft_history"] = _compact_draft_history(
                elem_dict["draft_history"]
            )
        
        # Keep only latest qa_history entry
        if elem_dict.get("qa_history") and len(elem_dict["qa_history"]) > 1:
            elem_dict["qa_history"] = [elem_dict["qa_history"][-1]]
        
        # Clear verbose fields
        elem_dict["qa_notes"] = []
        elem_dict["feedback"] = ""
        elem_dict["rewrite_reason"] = None
        
        compacted_elements[i] = elem_dict
    
    logger.info(f"Post-export compaction completed for {len(compacted_elements)} elements")
    
    return {
        "draft_elements": compacted_elements,
        # Clear transient fields
        "_field_mappings": None,
        "pending_question": None,
        "last_error": None,
        "validation_error": None,
    }


def clear_transient_fields(state: AgentState) -> dict:
    """
    Clear all transient fields.
    
    Called when handling errors or recovering from unexpected states.
    Safe to call at any time - only clears fields in TIER_3_TRANSIENT.
    
    Args:
        state: Current agent state
        
    Returns:
        State update dict with cleared transient fields
    """
    updates = {}
    
    for field in TIER_3_TRANSIENT:
        current_value = state.get(field)
        if current_value is not None:
            # Clear to appropriate empty value
            if field in ("fields_needing_confirmation", "missing_fields"):
                updates[field] = []
            else:
                updates[field] = None
    
    if updates:
        logger.debug(f"Cleared transient fields: {list(updates.keys())}")
    
    return updates


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _compact_draft_history(history: list) -> list[dict]:
    """
    Compact draft history to preserve metadata but reduce size.
    
    Keeps:
    - Attempt count (implicit from list length)
    - QA pass/fail status
    - Rewrite reason
    - User feedback presence (bool, not full text)
    
    Drops:
    - Full draft content (already superseded)
    - Verbose QA feedback text
    - Detailed failure lists
    
    Args:
        history: List of DraftAttempt dicts or DraftAttempt objects
        
    Returns:
        Compacted history with essential metadata only
    """
    if not history:
        return []
    
    compacted = []
    for attempt in history:
        # Handle both dict and DraftAttempt objects
        if isinstance(attempt, dict):
            compacted.append({
                "qa_passed": attempt.get("qa_passed", False),
                "rewrite_reason": attempt.get("rewrite_reason"),
                "had_user_feedback": bool(attempt.get("user_feedback")),
                # Drop: content, qa_feedback, qa_failures (verbose)
            })
        else:
            # It's a DraftAttempt Pydantic model
            compacted.append({
                "qa_passed": attempt.qa_passed,
                "rewrite_reason": attempt.rewrite_reason,
                "had_user_feedback": bool(attempt.user_feedback),
            })
    
    return compacted


def get_compaction_summary(state: AgentState) -> dict:
    """
    Get a summary of what would be compacted in current state.
    
    Useful for debugging and tracing. Does NOT modify state.
    
    Args:
        state: Current agent state
        
    Returns:
        Dict with compaction opportunity analysis
    """
    draft_elements = state.get("draft_elements", [])
    
    summary = {
        "phase": state.get("phase"),
        "transient_fields_set": [],
        "elements_with_history": [],
        "total_qa_history_entries": 0,
        "compaction_opportunities": [],
    }
    
    # Check transient fields
    for field in TIER_3_TRANSIENT:
        if state.get(field) is not None:
            value = state.get(field)
            if isinstance(value, list) and value:
                summary["transient_fields_set"].append(f"{field} ({len(value)} items)")
            elif value:
                summary["transient_fields_set"].append(field)
    
    # Check element histories
    for elem_dict in draft_elements:
        elem = DraftElement.model_validate(elem_dict)
        
        history_len = len(elem.draft_history) if elem.draft_history else 0
        qa_history_len = len(elem.qa_history) if elem.qa_history else 0
        
        summary["total_qa_history_entries"] += qa_history_len
        
        if history_len > 0 or qa_history_len > 1:
            summary["elements_with_history"].append({
                "name": elem.name,
                "status": elem.status,
                "draft_history_count": history_len,
                "qa_history_count": qa_history_len,
            })
            
            if elem.status == "approved":
                summary["compaction_opportunities"].append(
                    f"{elem.name}: approved with {history_len} draft history entries"
                )
    
    return summary


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Tier definitions (for documentation/testing)
    "TIER_1_NEVER_COMPACT",
    "ELEMENT_TIER_1_NEVER_COMPACT",
    "ELEMENT_TIER_2_COMPACT_AFTER_APPROVAL",
    "TIER_3_TRANSIENT",
    # Compaction functions
    "compact_after_interview",
    "compact_after_element_approved",
    "compact_after_export",
    "clear_transient_fields",
    # Utilities
    "get_compaction_summary",
]
