"""Intent classification node - analyzes user input to determine intent.

=======================================================================
NO MOCK LLM POLICY - This node ALWAYS requires a real LLM API call.
=======================================================================
This is a deliberate architectural decision. Mock LLM implementations:
- Create false confidence in tests that don't reflect production behavior
- Allow bugs in prompts and structured output to go undetected
- Add complexity with dual code paths that diverge over time

If you need to test without API calls, use VCR/cassette recording of real
LLM responses, NOT pattern-matching fallbacks.

See: AGENTS.MD, docs/modules/nodes.md for policy details
=======================================================================
"""

import logging
import os
import re
from typing import Any

from src.exceptions import ConfigurationError
from src.models.intent import IntentClassification
from src.models.state import AgentState
from src.prompts import get_template
from src.utils.llm import get_chat_model, traced_node, traced_structured_llm_call

logger = logging.getLogger(__name__)

# Structured action prefix — sent by element_action WebSocket protocol.
# Format: [ACTION:<action>:<element>] optional_feedback
# Bypasses LLM classification (allowed exception per CLAUDE.md).
_ACTION_PREFIX_RE = re.compile(r"^\[ACTION:(\w+):([^\]]+)\](?:\s+(.*))?$", re.DOTALL)


def _require_api_key() -> None:
    """Ensure OPENAI_API_KEY is configured. Raises ConfigurationError if missing."""
    if not os.getenv("OPENAI_API_KEY"):
        raise ConfigurationError(
            "OPENAI_API_KEY is required for intent classification. "
            "This agent does not support mock LLM fallbacks."
        )


def _get_last_assistant_message(state: AgentState) -> str | None:
    """Extract the last assistant message from state.
    
    This provides context for what question we asked the user,
    helping the classifier understand what kind of response to expect.
    
    Args:
        state: Current agent state with messages
        
    Returns:
        The last assistant message content, or None if not found
    """
    messages = state.get("messages", [])
    
    # Walk backwards to find the last AI message
    for msg in reversed(messages):
        # Check for AIMessage type (from langchain)
        if hasattr(msg, "type") and msg.type == "ai":
            return getattr(msg, "content", None)
        # Check for dict representation
        if isinstance(msg, dict) and msg.get("type") == "ai":
            return msg.get("content")
    
    return None


_SIMPLE_PATTERNS = re.compile(
    r"^("
    r"ye[sp]|yeah|yep|yup|sure|ok(ay)?|no|nah|nope|not really|"
    r"correct|right|that'?s (right|correct|good|fine|it)|"
    r"sounds good|looks good|that works|go ahead|"
    r"next( question)?|skip|continue|move on|"
    r"i'?m not sure|i don'?t know|no idea|"
    r"can you (explain|repeat|rephrase|clarify)( that)?|"
    r"what do you mean|help|thanks|thank you"
    r")\.?!?\s*$",
    re.IGNORECASE,
)


def _is_simple_message(text: str, current_field: str | None = None) -> bool:
    """Check if a message is simple enough to classify with the mini model.

    A message is simple if ALL of these are true:
    - No active field being asked about (field answers need structured extraction)
    - Word count <= 12
    - No digits (digits suggest field data: grades, series, employee counts)
    - No commas (commas suggest lists: duties, org hierarchy)
    - Is very short (<=4 words) OR matches common affirm/deny/nav patterns
    """
    # When a field is actively being asked, even "yes"/"no" carries field data
    # that requires accurate structured extraction (FieldMapping schema).
    # Mini struggles with this, so route to the full model.
    if current_field is not None:
        return False

    text = text.strip()
    words = text.split()
    word_count = len(words)

    if word_count > 12:
        return False
    if any(c.isdigit() for c in text):
        return False
    if "," in text:
        return False

    # Very short messages are almost always simple
    if word_count <= 4:
        return True

    # Longer (5-12 word) messages: only simple if they match known patterns
    return bool(_SIMPLE_PATTERNS.match(text))


async def classify_intent_with_llm(
    user_message: str,
    state: AgentState,
) -> IntentClassification:
    """
    Classify intent using LLM with structured output.

    Uses a streamlined prompt with minimal context:
    - Last user message (provided)
    - Last assistant message (for response context)
    - Current phase
    - Current field being asked about (if any)

    This reduces token usage by ~70% compared to the full template
    while maintaining classification accuracy.

    Args:
        user_message: The user's message to classify
        state: Current agent state for context

    Returns:
        IntentClassification with detected intent and field mappings
    """
    # Import here to avoid circular imports and allow graceful degradation
    from src.utils import get_structured_llm

    # Get last assistant message for context
    last_assistant_message = _get_last_assistant_message(state)

    # Build minimal context for template - only what's needed for routing
    context: dict[str, Any] = {
        "phase": state.get("phase", "init"),
        "current_field": state.get("current_field"),
        "last_assistant_message": last_assistant_message,
        "user_message": user_message,
    }

    # Use the lite template with reduced context
    template = get_template("intent_classification_lite.jinja")
    prompt = template.render(**context)

    # Use mini model for simple phases (init/drafting/requirements) where intents
    # are straightforward (confirm, approve, quit). For interview phase, use mini
    # for simple messages (confirms, denials, navigation) but keep full model for
    # complex messages with field data (numbers, lists, detailed descriptions).
    phase = context["phase"]
    if phase in ("init", "drafting", "requirements"):
        model = "gpt-4o-mini"
    elif _is_simple_message(user_message, current_field=context["current_field"]):
        model = "gpt-4o-mini"
    else:
        model = None  # uses default (gpt-5.2)
    llm = get_chat_model(model=model)

    # Call LLM with tracing
    result, _usage = await traced_structured_llm_call(
        llm=llm,
        prompt=prompt,
        output_schema=IntentClassification,
        node_name="intent_classification",
        metadata={"phase": context["phase"], "current_field": context["current_field"]},
    )

    return result


_ACTION_INTENT_MAP = {
    "approve": "confirm",
    "reject": "reject",
    "regenerate": "modify_answer",
}


def _classify_structured_action(match: re.Match) -> dict[str, Any]:
    """Short-circuit classification for structured element actions.

    Maps element_action protocol actions to intents without LLM call.
    This is an allowed exception per CLAUDE.md policy.
    """
    action = match.group(1)
    element = match.group(2)
    feedback = (match.group(3) or "").strip()

    intent = _ACTION_INTENT_MAP.get(action, "unrecognized")
    logger.info("Structured action: %s on %s → intent=%s", action, element, intent)

    result: dict[str, Any] = {
        "last_intent": intent,
        "_structured_action": {
            "action": action,
            "element": element,
            "feedback": feedback,
        },
    }

    # For regenerate with feedback, include modification details
    if action == "regenerate" and feedback:
        result["_modification"] = {
            "field": element,
            "new_value": feedback,
        }

    return result


@traced_node
async def intent_classification_node(state: AgentState) -> dict:
    """
    Classify user intent from their last message (async LLM version).

    Uses LLM with structured output for full classification including
    field extraction when appropriate.
    
    ALWAYS uses real LLM - no mock/pattern-matching fallbacks.

    Args:
        state: Current agent state with messages

    Returns:
        State update with classified intent and optional field mappings
        
    Raises:
        ConfigurationError: If OPENAI_API_KEY is not configured
    """
    # Require API key - no fallback allowed
    _require_api_key()

    # Get the last user message
    messages = state.get("messages", [])
    if not messages:
        return {
            "last_intent": "unrecognized",
        }

    last_message = messages[-1]
    user_content = getattr(last_message, "content", str(last_message))

    # Structured action short-circuit — element_action protocol bypasses LLM.
    # This is an allowed exception per CLAUDE.md (simple binary conditions).
    action_match = _ACTION_PREFIX_RE.match(user_content)
    if action_match:
        return _classify_structured_action(action_match)

    # Always use LLM for classification
    classification = await classify_intent_with_llm(user_content, state)
    result: dict[str, Any] = {
        "last_intent": classification.primary_intent,
        # Store full classification for downstream nodes that need structured details
        "intent_classification": classification,
    }

    # Include field mappings if present (for provide_information intent)
    if classification.field_mappings:
        result["_field_mappings"] = [
            m.model_dump() for m in classification.field_mappings
        ]

    # Include question details if present
    if classification.primary_intent == "ask_question" and classification.question:
        result["pending_question"] = classification.question

    # Include modification details if present
    if classification.primary_intent == "modify_answer":
        result["_modification"] = {
            "field": classification.field_to_modify,
            "new_value": classification.new_value,
        }

    # Include export request if present (for request_export intent)
    if classification.export_request:
        result["_export_request"] = classification.export_request.model_dump()

    return result
