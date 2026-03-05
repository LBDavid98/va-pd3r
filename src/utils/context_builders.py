"""Context builders for LLM prompts in PD3r.

This module provides context selectors that build minimal, focused context
for each LLM prompt. This is the PRIMARY optimization mechanism for reducing
token usage while maintaining output quality.

ARCHITECTURE: Dense State / Light Prompts
=========================================
The key insight is that we DON'T need to compact state to reduce costs.
Instead, we keep full state (for debugging, export, user queries) but
SELECT only the relevant context for each prompt.

Benefits:
- Full state available for debugging and export
- Each prompt gets exactly what it needs
- Token usage scales with task complexity, not state size
- Easy to tune per-prompt context for quality improvements

POST-MVP OPTIMIZATION OPPORTUNITIES
====================================
This module is designed for iterative quality improvements. Each context
builder has explicit sections marked with "# QUALITY TUNING:" comments
that identify fields which may benefit from adjustment.

Quality tuning workflow:
1. Run agent with tracing enabled
2. Analyze trace for prompt sizes and output quality
3. Identify context fields that could be added/removed
4. Update context builder
5. Run comparison trace
6. Measure quality impact

Key tuning decisions per prompt type:

INTENT CLASSIFICATION:
    Current: phase, current_field, last_message, user_input
    Potential additions:
    - draft_status_summary (helps classify drafting-phase requests)
    - recent_questions (helps detect repeated questions)
    - field_history (helps with multi-field extraction confidence)

ELEMENT GENERATION:
    Current: section config, interview fields for section, FES targets
    Potential additions:
    - sibling_content (helps maintain consistency across sections)
    - qa_patterns (helps avoid known failure modes)
    - user_style_preferences (if captured during interview)

QA REVIEW:
    Current: draft content, requirements checklist
    Potential additions:
    - interview_evidence (verbatim quotes supporting claims)
    - previous_failures (prevents repeated mistakes)
    - element_dependencies (context from prerequisite sections)

REWRITE PROMPTS:
    Current: original draft, QA failures, user feedback
    Potential additions:
    - successful_patterns (from elements that passed QA)
    - failure_analysis (deeper reasoning about what went wrong)

CONTEXT BUILDER INTERFACE
=========================
Each context builder follows the pattern:

    def build_<task>_context(
        state: AgentState,
        **task_specific_params
    ) -> dict:
        '''
        Build minimal context for <task>.
        
        Args:
            state: Full agent state
            **task_specific_params: Task-specific parameters
            
        Returns:
            Dict with only the fields needed for this prompt
        '''

The returned dict should be directly usable as template context.

TESTING
=======
Each context builder has tests that verify:
- All required fields are present (completeness)
- No unnecessary fields are included (minimality)
- Output matches expected structure (correctness)
- Token estimates are within bounds (efficiency)

See: tests/test_context_builders.py

METRICS
=======
Context builders track metrics via structured logging:
- Fields included vs available
- Estimated token count
- Context build time

Enable with: LOG_CONTEXT_METRICS=true
"""

import logging
import os
from typing import Any, Optional

from src.models.draft import DraftElement
from src.models.interview import InterviewData
from src.models.requirements import DraftRequirements

# Try to import FES evaluation - may not exist in minimal configs
try:
    from src.models.fes import FESEvaluation
except ImportError:
    FESEvaluation = None

# Try to import section registry
try:
    from src.config.drafting_sections import SECTION_REGISTRY
except ImportError:
    SECTION_REGISTRY = {}

logger = logging.getLogger(__name__)

# Enable context metrics logging
LOG_CONTEXT_METRICS = os.environ.get("LOG_CONTEXT_METRICS", "").lower() == "true"


# ============================================================================
# INTENT CLASSIFICATION CONTEXT
# ============================================================================

def build_intent_classification_context(
    state: dict,
    user_message: str,
) -> dict:
    """
    Build minimal context for intent classification.
    
    Intent classification needs to understand:
    - Current conversation phase (what intents are valid)
    - What we're asking about (current_field during interview)
    - Recent context (last assistant message)
    - User's response (to classify)
    
    DOES NOT need:
    - Full message history (only last assistant message)
    - Draft content (not relevant for classification)
    - QA details (not relevant for classification)
    - FES evaluation details
    
    Args:
        state: Full agent state
        user_message: The user message to classify
        
    Returns:
        Context dict for intent classification template
        
    QUALITY TUNING:
        - Add `draft_status_summary` if drafting-phase classification is poor
        - Add `recent_field_values` if multi-field extraction is unreliable
        - Add `confirmation_context` if confirmation intents are mis-classified
    """
    # Get last assistant message for context
    messages = state.get("messages", [])
    last_assistant_message = ""
    for msg in reversed(messages):
        if hasattr(msg, "type") and msg.type == "ai":
            last_assistant_message = msg.content
            break
        elif isinstance(msg, dict) and msg.get("type") == "ai":
            last_assistant_message = msg.get("content", "")
            break
    
    # Get recent conversation exchanges for broader context
    recent_exchanges = _get_recent_conversation(messages, max_turns=3)

    context = {
        # Phase determines valid intents
        "phase": state.get("phase", "init"),

        # Current field being asked (None if not in interview)
        "current_field": state.get("current_field"),

        # Last assistant message for conversational context
        "last_assistant_message": last_assistant_message,

        # Recent conversation for multi-turn understanding
        "recent_exchanges": recent_exchanges,

        # User message to classify
        "user_message": user_message,
    }
    
    # QUALITY TUNING: Add phase-specific context
    phase = state.get("phase")
    
    if phase == "interview":
        # Add fields that need confirmation if any
        context["fields_needing_confirmation"] = state.get(
            "fields_needing_confirmation", []
        )
        # Add missing fields count for progress context
        context["missing_fields_count"] = len(state.get("missing_fields", []))
    
    elif phase == "drafting":
        # Add draft progress summary
        draft_elements = state.get("draft_elements", [])
        if draft_elements:
            context["draft_progress"] = _get_draft_progress_summary(draft_elements)
    
    elif phase == "review":
        # Add current element context
        context["current_element_name"] = state.get("current_element_name")
    
    _log_context_metrics("intent_classification", context, state)
    
    return context


# ============================================================================
# ELEMENT GENERATION CONTEXT
# ============================================================================

def build_generation_context(
    state: dict,
    element_name: str,
    is_rewrite: bool = False,
) -> dict:
    """
    Build context for element generation prompts.
    
    Element generation needs:
    - Section configuration (what to generate)
    - Relevant interview data (only fields this section needs)
    - FES evaluation targets (for factor sections)
    - Requirements for this section (QA expectations)
    - For rewrites: previous attempt info and failures
    
    DOES NOT need:
    - Other elements' content (except prerequisites)
    - Full interview data (only required fields)
    - QA history of other elements
    - Message history
    
    Args:
        state: Full agent state
        element_name: Name of element being generated
        is_rewrite: Whether this is a rewrite attempt
        
    Returns:
        Context dict for generation template
        
    QUALITY TUNING:
        - Add `sibling_content` if sections are inconsistent in style
        - Add `successful_patterns` if rewrites repeat same mistakes
        - Add `user_preferences` if user has expressed style preferences
    """
    # Get section configuration
    section_config = SECTION_REGISTRY.get(element_name, {})
    required_fields = section_config.get("requires", [])
    
    # Get interview data and extract only required fields
    interview_dict = state.get("interview_data", {})
    interview_data = _extract_required_interview_fields(
        interview_dict, required_fields
    )
    
    # Get FES evaluation for factor sections
    fes_context = None
    factor_id = section_config.get("factor_id")
    if factor_id:
        fes_dict = state.get("fes_evaluation")
        if fes_dict:
            fes_context = _extract_factor_context(fes_dict, factor_id)
    
    # Get requirements for this section
    requirements_context = None
    reqs_dict = state.get("draft_requirements")
    if reqs_dict:
        requirements_context = _extract_section_requirements(reqs_dict, element_name)
    
    context = {
        # Section metadata
        "section_name": element_name,
        "section_display_name": section_config.get(
            "description", element_name.replace("_", " ").title()
        ),
        "section_style": section_config.get("style", "narrative"),
        
        # Interview data (filtered to required fields)
        "interview_data": interview_data,
        
        # FES targets (for factor sections)
        "factor_targets": fes_context,
        
        # Requirements (for QA alignment)
        "requirements": requirements_context,
        
        # Rewrite flag
        "is_rewrite": is_rewrite,
    }
    
    # QUALITY TUNING: Add prerequisite content for context
    # Get prerequisites from the element itself (defined in draft model)
    prerequisites = _get_element_prerequisites(state.get("draft_elements", []), element_name)
    if prerequisites:
        context["prerequisite_content"] = _get_prerequisite_content(
            state.get("draft_elements", []), prerequisites
        )
    
    # QUALITY TUNING: Add rewrite context
    if is_rewrite:
        rewrite_context = _build_rewrite_context(state, element_name)
        context.update(rewrite_context)
    
    _log_context_metrics("element_generation", context, state)
    
    return context


def build_rewrite_context(
    state: dict,
    element_name: str,
) -> dict:
    """
    Build context specifically for rewrite prompts.
    
    Rewrites need everything from generation PLUS:
    - Original draft content
    - QA feedback and failures
    - User feedback (if any)
    - Previous attempt history
    
    Args:
        state: Full agent state
        element_name: Name of element being rewritten
        
    Returns:
        Context dict for rewrite template
        
    QUALITY TUNING:
        - Add `successful_examples` from other sections that passed QA
        - Add `failure_patterns` to help avoid common mistakes
        - Add `specific_fixes` with actionable rewrite guidance
    """
    # Start with generation context
    context = build_generation_context(state, element_name, is_rewrite=True)
    
    # Add rewrite-specific context
    rewrite_context = _build_rewrite_context(state, element_name)
    context.update(rewrite_context)
    
    _log_context_metrics("rewrite", context, state)
    
    return context


# ============================================================================
# QA REVIEW CONTEXT
# ============================================================================

def build_qa_review_context(
    state: dict,
    element_name: str,
) -> dict:
    """
    Build context for QA review prompts.
    
    QA review needs:
    - Draft content to review
    - Requirements checklist for this section
    - Section-specific evaluation criteria
    
    DOES NOT need:
    - Other elements (reviewed independently)
    - Full interview data (requirements capture intent)
    - FES evaluation (requirements capture expectations)
    - Message history
    
    Args:
        state: Full agent state
        element_name: Name of element being reviewed
        
    Returns:
        Context dict for QA review template
        
    QUALITY TUNING:
        - Add `interview_evidence` to verify claims against source
        - Add `previous_qa_failures` to check for regression
        - Add `style_requirements` for consistency checks
    """
    # Get the element being reviewed
    draft_elements = state.get("draft_elements", [])
    element = None
    for elem_dict in draft_elements:
        elem = DraftElement.model_validate(elem_dict)
        if elem.name == element_name:
            element = elem
            break
    
    if not element:
        logger.warning(f"Element {element_name} not found for QA context")
        return {}
    
    # Get requirements for this section
    requirements_context = []
    reqs_dict = state.get("draft_requirements")
    if reqs_dict:
        requirements_context = _extract_section_requirements(reqs_dict, element_name)
    
    context = {
        # Section identification
        "section_name": element_name,
        "section_display_name": element.display_name,
        
        # Content to review
        "draft_content": element.content,
        
        # Requirements checklist
        "requirements": requirements_context,
        
        # Review metadata
        "attempt_number": element.attempt_number,
        "is_rewrite": element.is_rewrite,
    }
    
    # QUALITY TUNING: Add previous QA context for rewrites
    if element.qa_history:
        context["previous_failures"] = _summarize_qa_failures(element.qa_history)
    
    _log_context_metrics("qa_review", context, state)
    
    return context


# ============================================================================
# ANSWER QUESTION CONTEXT
# ============================================================================

def build_answer_question_context(
    state: dict,
    question: str,
) -> dict:
    """
    Build context for answering user questions.
    
    Question answering may need:
    - The question being asked
    - Relevant interview data (for "what did I say about X" questions)
    - Current draft status (for "where are we" questions)
    - Recent conversation context
    
    Context is question-dependent - we include more if the question
    seems to require it.
    
    Args:
        state: Full agent state
        question: The user's question
        
    Returns:
        Context dict for answer question template
        
    QUALITY TUNING:
        - Improve question classification to select relevant context
        - Add RAG integration for knowledge base questions
        - Add draft content access for "show me X" questions
    """
    context = {
        "question": question,
        "phase": state.get("phase", "init"),
    }
    
    # Always include interview summary for reference questions
    interview_dict = state.get("interview_data")
    if interview_dict:
        try:
            interview = InterviewData.model_validate(interview_dict)
            context["interview_summary"] = interview.to_summary_dict()
        except Exception:
            context["interview_summary"] = {}
    
    # Add draft status if in drafting/review phase
    phase = state.get("phase")
    if phase in ("drafting", "review", "complete"):
        draft_elements = state.get("draft_elements", [])
        if draft_elements:
            context["draft_status"] = _get_draft_status_detail(draft_elements)
    
    # Add recent conversation context
    messages = state.get("messages", [])
    if messages:
        context["recent_context"] = _get_recent_conversation(messages, max_turns=3)
    
    _log_context_metrics("answer_question", context, state)
    
    return context


# ============================================================================
# EXPORT CONTEXT
# ============================================================================

def build_export_context(state: dict) -> dict:
    """
    Build context for document export.
    
    Export needs:
    - All approved draft elements with content
    - Interview data for headers and metadata
    - Export configuration
    
    This is one case where we need MORE context, not less,
    because we're assembling the final document.
    
    Args:
        state: Full agent state
        
    Returns:
        Context dict for export operations
    """
    context = {
        "draft_elements": state.get("draft_elements", []),
        "interview_data": state.get("interview_data", {}),
        "fes_evaluation": state.get("fes_evaluation", {}),
        "phase": state.get("phase"),
    }
    
    _log_context_metrics("export", context, state)
    
    return context


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _extract_required_interview_fields(
    interview_dict: dict,
    required_fields: list[str],
) -> dict:
    """
    Extract only the required fields from interview data.
    
    Args:
        interview_dict: Full serialized InterviewData
        required_fields: List of field names needed
        
    Returns:
        Dict with only required fields and their values
    """
    if not interview_dict:
        return {}
    
    try:
        interview = InterviewData.model_validate(interview_dict)
    except Exception:
        return {}
    
    extracted = {}
    
    # Handle special composite fields
    field_mapping = {
        "factor_targets": None,  # Handled separately via FES
        "factor_context": None,  # Handled separately via FES
    }
    
    for field_name in required_fields:
        if field_name in field_mapping:
            continue  # Skip composite fields
            
        if hasattr(interview, field_name):
            field_element = getattr(interview, field_name)
            if hasattr(field_element, "is_set") and field_element.is_set:
                extracted[field_name] = field_element.value
    
    return extracted


def _extract_factor_context(fes_dict: dict, factor_id: str) -> dict:
    """
    Extract FES factor context for a specific factor.
    
    Args:
        fes_dict: Full serialized FESEvaluation
        factor_id: Factor ID (e.g., "1", "6_7")
        
    Returns:
        Dict with factor targets and level info
    """
    if not fes_dict or not FESEvaluation:
        return {}
    
    try:
        fes = FESEvaluation.model_validate(fes_dict)
        
        # Get factor from evaluation
        factor_attr = f"factor_{factor_id}"
        if hasattr(fes, factor_attr):
            factor = getattr(fes, factor_attr)
            return {
                "level": getattr(factor, "level", None),
                "points": getattr(factor, "points", None),
                "justification": getattr(factor, "justification", ""),
            }
    except Exception:
        pass
    
    return {}


def _extract_section_requirements(reqs_dict: dict, element_name: str) -> list[dict]:
    """
    Extract requirements for a specific section.
    
    Args:
        reqs_dict: Full serialized DraftRequirements
        element_name: Section name
        
    Returns:
        List of requirement dicts for this section
    """
    if not reqs_dict:
        return []
    
    try:
        requirements = DraftRequirements.model_validate(reqs_dict)
        section_reqs = requirements.get_requirements_for_element(element_name)
        
        return [
            {
                "id": req.id,
                "description": req.description,
                "is_critical": req.is_critical,
                "check_type": req.check_type,
            }
            for req in section_reqs
        ]
    except Exception:
        return []


def _get_prerequisite_content(
    draft_elements: list[dict],
    prerequisites: list[str],
) -> dict:
    """
    Get content from prerequisite elements.
    
    Args:
        draft_elements: List of serialized DraftElement dicts
        prerequisites: List of prerequisite element names
        
    Returns:
        Dict mapping prerequisite name to content
    """
    content = {}
    
    for elem_dict in draft_elements:
        try:
            elem = DraftElement.model_validate(elem_dict)
            if elem.name in prerequisites and elem.content:
                content[elem.name] = elem.content
        except Exception:
            continue
    
    return content


def _build_rewrite_context(state: dict, element_name: str) -> dict:
    """
    Build rewrite-specific context from element history.
    
    Args:
        state: Full agent state
        element_name: Name of element being rewritten
        
    Returns:
        Dict with rewrite context
    """
    draft_elements = state.get("draft_elements", [])
    
    for elem_dict in draft_elements:
        try:
            elem = DraftElement.model_validate(elem_dict)
            if elem.name == element_name:
                return elem.get_rewrite_context()
        except Exception:
            continue
    
    return {}


def _get_element_prerequisites(
    draft_elements: list[dict],
    element_name: str,
) -> list[str]:
    """
    Get prerequisites for a specific element from the draft elements list.
    
    Args:
        draft_elements: List of serialized DraftElement dicts
        element_name: Name of element to find prerequisites for
        
    Returns:
        List of prerequisite element names
    """
    for elem_dict in draft_elements:
        try:
            elem = DraftElement.model_validate(elem_dict)
            if elem.name == element_name:
                return elem.prerequisites
        except Exception:
            continue
    
    return []


def _get_draft_progress_summary(draft_elements: list[dict]) -> dict:
    """
    Get a compact summary of draft progress.
    
    Args:
        draft_elements: List of serialized DraftElement dicts
        
    Returns:
        Dict with progress metrics
    """
    total = len(draft_elements)
    approved = 0
    qa_passed = 0
    drafting = 0
    pending = 0
    
    for elem_dict in draft_elements:
        status = elem_dict.get("status", "pending")
        if status == "approved":
            approved += 1
        elif status == "qa_passed":
            qa_passed += 1
        elif status in ("drafted", "needs_revision"):
            drafting += 1
        else:
            pending += 1
    
    return {
        "total": total,
        "approved": approved,
        "qa_passed": qa_passed,
        "in_progress": drafting,
        "pending": pending,
        "percent_complete": round((approved + qa_passed) / total * 100) if total > 0 else 0,
    }


def _get_draft_status_detail(draft_elements: list[dict]) -> list[dict]:
    """
    Get detailed status of each draft element.
    
    Args:
        draft_elements: List of serialized DraftElement dicts
        
    Returns:
        List of status dicts
    """
    statuses = []
    
    for elem_dict in draft_elements:
        try:
            elem = DraftElement.model_validate(elem_dict)
            statuses.append({
                "name": elem.display_name or elem.name,
                "status": elem.status,
                "has_content": bool(elem.content),
                "revision_count": elem.revision_count,
            })
        except Exception:
            continue
    
    return statuses


def _summarize_qa_failures(qa_history: list[dict]) -> list[str]:
    """
    Summarize QA failures from history.
    
    Args:
        qa_history: List of QA review dicts
        
    Returns:
        List of failure summaries
    """
    failures = []
    
    for qa_dict in qa_history:
        if not qa_dict.get("passes", True):
            feedback = qa_dict.get("overall_feedback", "")
            if feedback:
                failures.append(feedback[:200])  # Truncate long feedback
    
    return failures


def _get_recent_conversation(messages: list, max_turns: int = 3) -> list[dict]:
    """
    Get recent conversation turns.
    
    Args:
        messages: Message history
        max_turns: Maximum turns to include
        
    Returns:
        List of recent message dicts
    """
    recent = []
    turn_count = 0
    
    for msg in reversed(messages):
        if turn_count >= max_turns:
            break
            
        msg_dict = {}
        if hasattr(msg, "type"):
            msg_dict["type"] = msg.type
            msg_dict["content"] = msg.content[:500]  # Truncate
        elif isinstance(msg, dict):
            msg_dict["type"] = msg.get("type", "unknown")
            msg_dict["content"] = msg.get("content", "")[:500]
        
        if msg_dict:
            recent.append(msg_dict)
            if msg_dict["type"] == "human":
                turn_count += 1
    
    return list(reversed(recent))


def _log_context_metrics(
    context_type: str,
    context: dict,
    full_state: dict,
) -> None:
    """
    Log context builder metrics for analysis.
    
    Args:
        context_type: Type of context built
        context: The built context
        full_state: Full state for comparison
    """
    if not LOG_CONTEXT_METRICS:
        return
    
    # Estimate token count (rough: 4 chars ≈ 1 token)
    import json
    context_str = json.dumps(context, default=str)
    estimated_tokens = len(context_str) // 4
    
    state_str = json.dumps(full_state, default=str)
    full_tokens = len(state_str) // 4
    
    reduction = round((1 - estimated_tokens / full_tokens) * 100) if full_tokens > 0 else 0
    
    logger.info(
        f"Context metrics [{context_type}]: "
        f"~{estimated_tokens} tokens (vs {full_tokens} full state, "
        f"{reduction}% reduction)"
    )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Primary context builders
    "build_intent_classification_context",
    "build_generation_context",
    "build_rewrite_context",
    "build_qa_review_context",
    "build_answer_question_context",
    "build_export_context",
    # Utilities (for testing)
    "_extract_required_interview_fields",
    "_extract_factor_context",
    "_extract_section_requirements",
    "_get_prerequisite_content",
    "_get_draft_progress_summary",
]
