"""Personality utilities - phrase rotation and Pete's conversational variety.

Pete's Voice Guidelines (from Appendix C):
- Friendly, professional, and slightly playful
- Uses contractions ("I'm", "you're", "that's")
- Acknowledges user input positively
- Uses first person and addresses user directly
- Offers brief explanations when redirecting
- Has light humor at natural moments

This module provides phrase rotation to avoid repetitive responses.
"""

import random

# =============================================================================
# ACKNOWLEDGMENT PHRASES
# Used after successfully mapping user answers
# =============================================================================

ACKNOWLEDGMENT_PHRASES = [
    "Great, I've mapped your answers:",
    "Got it! Here's what I captured:",
    "Perfect, I've recorded:",
    "Thanks! I've noted:",
    "Excellent! I've got:",
    "Great, here's what I have:",
    "Awesome, captured:",
]

# =============================================================================
# TRANSITION PHRASES
# Used when moving between topics or fields
# =============================================================================

TRANSITION_PHRASES = [
    "Next, I need to know",
    "Moving on:",
    "Up next:",
    "Now let's talk about",
    "Next up:",
    "Now I'll need",
    "Let's move to",
]

# =============================================================================
# WORKING PHRASES
# Used during generation or processing
# =============================================================================

WORKING_PHRASES = [
    "Just a moment...",
    "Working on that...",
    "Let me put that together...",
    "One sec while I draft that...",
    "Sure thing, give me a moment...",
    "Let me work on that...",
    "Drafting that up...",
]

# =============================================================================
# COMPLETION PHRASES
# Used when presenting generated content
# =============================================================================

COMPLETION_PHRASES = [
    "Here you go:",
    "Here's what I came up with:",
    "Take a look:",
    "How's this?",
    "Check this out:",
    "Here's the draft:",
    "Let me know what you think:",
]

# =============================================================================
# CONFIRMATION SUCCESS PHRASES
# Used when user confirms something
# =============================================================================

CONFIRMATION_SUCCESS_PHRASES = [
    "Great!",
    "Perfect!",
    "Excellent!",
    "Awesome!",
    "Got it!",
    "Sounds good!",
    "All set!",
]

# =============================================================================
# REVISION ACKNOWLEDGMENT PHRASES
# Used when user requests changes
# =============================================================================

REVISION_ACKNOWLEDGMENT_PHRASES = [
    "Thanks, I'll work that into the draft.",
    "Got it, let me update that.",
    "Sure thing, I'll revise that.",
    "No problem, updating now.",
    "Understood, making those changes.",
    "On it, let me rework that.",
]

# =============================================================================
# BACK TO TOPIC PHRASES
# Used after answering a question to return to flow
# =============================================================================

BACK_TO_TOPIC_PHRASES = [
    "Back to our PD:",
    "Now, back to the position description:",
    "Anyway, back to where we were:",
    "Now, continuing with our PD:",
    "Getting back on track:",
]


# =============================================================================
# State-aware rotation to avoid repeating the same phrase
# =============================================================================

_last_used: dict[str, int] = {}


def _get_phrase_with_rotation(
    phrases: list[str],
    category: str,
    avoid_last_n: int = 2,
) -> str:
    """
    Get a phrase from a list, avoiding recently used ones.

    Args:
        phrases: List of phrase options
        category: Category name for tracking (e.g., "acknowledgment")
        avoid_last_n: Number of recent phrases to avoid

    Returns:
        Selected phrase
    """
    if len(phrases) <= avoid_last_n:
        # If we don't have enough variety, just pick randomly
        return random.choice(phrases)

    # Get last used index for this category
    last_idx = _last_used.get(category)

    # Build list of candidates (indices to avoid)
    if last_idx is not None:
        # Avoid the last N used (wrap around)
        avoid_indices = set()
        for i in range(avoid_last_n):
            avoid_indices.add((last_idx - i) % len(phrases))
        candidates = [i for i in range(len(phrases)) if i not in avoid_indices]
    else:
        candidates = list(range(len(phrases)))

    # Pick randomly from candidates
    chosen_idx = random.choice(candidates)
    _last_used[category] = chosen_idx

    return phrases[chosen_idx]


def reset_phrase_history() -> None:
    """Reset the phrase rotation history. Useful for testing."""
    _last_used.clear()


# =============================================================================
# Public API - phrase getters
# =============================================================================


def get_acknowledgment() -> str:
    """Get an acknowledgment phrase with rotation."""
    return _get_phrase_with_rotation(ACKNOWLEDGMENT_PHRASES, "acknowledgment")


def get_transition() -> str:
    """Get a transition phrase with rotation."""
    return _get_phrase_with_rotation(TRANSITION_PHRASES, "transition")


def get_working() -> str:
    """Get a working/processing phrase with rotation."""
    return _get_phrase_with_rotation(WORKING_PHRASES, "working")


def get_completion() -> str:
    """Get a completion phrase with rotation."""
    return _get_phrase_with_rotation(COMPLETION_PHRASES, "completion")


def get_confirmation_success() -> str:
    """Get a confirmation success phrase with rotation."""
    return _get_phrase_with_rotation(CONFIRMATION_SUCCESS_PHRASES, "confirmation")


def get_revision_acknowledgment() -> str:
    """Get a revision acknowledgment phrase with rotation."""
    return _get_phrase_with_rotation(REVISION_ACKNOWLEDGMENT_PHRASES, "revision")


def get_back_to_topic() -> str:
    """Get a 'back to topic' phrase with rotation."""
    return _get_phrase_with_rotation(BACK_TO_TOPIC_PHRASES, "back_to_topic")


# =============================================================================
# Convenience functions for building responses
# =============================================================================


def acknowledge_and_list(items: list[str]) -> str:
    """
    Build an acknowledgment response with a bulleted list.

    Args:
        items: List of items to display

    Returns:
        Formatted response string

    Example:
        >>> acknowledge_and_list(["Position Title: IT Specialist", "Series: 2210"])
        "Got it! Here's what I captured:\n- Position Title: IT Specialist\n- Series: 2210"
    """
    ack = get_acknowledgment()
    if not items:
        return ack
    item_list = "\n".join(f"- {item}" for item in items)
    return f"{ack}\n{item_list}"


def transition_to(next_topic: str) -> str:
    """
    Build a transition response to the next topic.

    Args:
        next_topic: The next topic or field to discuss

    Returns:
        Formatted transition string

    Example:
        >>> transition_to("the grade level")
        "Next, I need to know the grade level"
    """
    trans = get_transition()
    # Some transitions already have punctuation, handle gracefully
    if trans.endswith(":"):
        return f"{trans} {next_topic}"
    return f"{trans} {next_topic}"


def present_draft(element_name: str) -> str:
    """
    Build a presentation response for a draft element.

    Args:
        element_name: Name of the element being presented

    Returns:
        Formatted presentation string

    Example:
        >>> present_draft("Introduction")
        "Here's what I came up with for the **Introduction**:"
    """
    comp = get_completion()
    if comp.endswith("?"):
        # "How's this?" doesn't need "for the X"
        return f"{comp}\n\n**{element_name}**"
    return f"{comp.rstrip(':')} for the **{element_name}**:"
