"""LLM client utilities for PD3r.

This module re-exports from src/utils/llm.py for backward compatibility.
New code should import directly from src.utils.llm for full functionality.
"""

# Re-export everything from the new llm module
from src.utils.llm import (
    # Configuration constants
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    MAX_RETRIES,
    TIMEOUT,
    REWRITE_MODEL,
    REWRITE_TEMPERATURE,
    MODEL_ESCALATION_MAP,
    MODEL_COSTS,
    # LLM client factories
    get_chat_model,
    get_rewrite_model,
    get_model_for_attempt,
    get_structured_llm,
    # Tracing
    is_tracing_enabled,
    start_run_trace,
    trace_node,
    trace_llm_call,
    finalize_node_trace,
    save_trace_log,
    get_trace_context,
    # Retry
    exponential_backoff_retry,
    # Traced LLM calls
    traced_llm_call,
    traced_llm_call_sync,
    traced_structured_llm_call,
)

__all__ = [
    "DEFAULT_MODEL",
    "DEFAULT_TEMPERATURE",
    "MAX_RETRIES",
    "TIMEOUT",
    "REWRITE_MODEL",
    "REWRITE_TEMPERATURE",
    "MODEL_ESCALATION_MAP",
    "MODEL_COSTS",
    "get_chat_model",
    "get_rewrite_model",
    "get_model_for_attempt",
    "get_structured_llm",
    "is_tracing_enabled",
    "start_run_trace",
    "trace_node",
    "trace_llm_call",
    "finalize_node_trace",
    "save_trace_log",
    "get_trace_context",
    "exponential_backoff_retry",
    "traced_llm_call",
    "traced_llm_call_sync",
    "traced_structured_llm_call",
    # Procedural generators for tiered generation
    "generate_procedural_content",
    "is_procedural_section",
    # State compaction utilities
    "compact_after_interview",
    "compact_after_element_approved",
    "compact_after_export",
    "clear_transient_fields",
    # Context builders for optimized prompts
    "build_intent_classification_context",
    "build_generation_context",
    "build_rewrite_context",
    "build_qa_review_context",
    "build_answer_question_context",
    "build_export_context",
]

# Procedural generator exports
from src.utils.procedural_generators import (
    generate_procedural_content,
    is_procedural_section,
)

# State compaction exports
from src.utils.state_compactor import (
    compact_after_interview,
    compact_after_element_approved,
    compact_after_export,
    clear_transient_fields,
)

# Context builder exports
from src.utils.context_builders import (
    build_intent_classification_context,
    build_generation_context,
    build_rewrite_context,
    build_qa_review_context,
    build_answer_question_context,
    build_export_context,
)
