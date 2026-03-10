"""LLM client utilities with tracing, retry, and error handling for PD3r.

This module provides:
- Configurable LLM clients (ChatOpenAI)
- Exponential backoff retry logic
- Toggle-able local tracing with cost tracking
- Model escalation for rewrites

Environment Variables:
- LOCAL_TRACING: Set to 'true' to enable local tracing
- OPENAI_DEFAULT_MODEL: Default model to use (default: gpt-4o)
- OPENAI_REWRITE_MODEL: Model for rewrite attempts (default: gpt-4o)
- OPENAI_MAX_RETRIES: Max retries for LLM calls (default: 3)
- OPENAI_TIMEOUT: Request timeout in seconds (default: 60)
"""

import asyncio
import json
import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Generator, TypeVar

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.types import Interrupt
from pydantic import BaseModel

from src.exceptions import (
    LLMConnectionError,
    LLMRateLimitError,
    LLMResponseError,
    LLMRetryExhaustedError,
    LLMTimeoutError,
    is_retryable,
)

T = TypeVar("T", bound=BaseModel)

# =============================================================================
# Configuration
# =============================================================================

DEFAULT_MODEL = os.getenv("OPENAI_DEFAULT_MODEL", "gpt-4o")
DEFAULT_TEMPERATURE = 0.3  # Slight creativity for drafting
MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "3"))
TIMEOUT = int(os.getenv("OPENAI_TIMEOUT", "60"))

# Rewrite-specific configuration
REWRITE_MODEL = os.getenv("OPENAI_REWRITE_MODEL", "gpt-4o")
REWRITE_TEMPERATURE = 0.1  # Lower temperature for more focused output

# Model escalation mapping - base model → escalated model for rewrites
MODEL_ESCALATION_MAP = {
    "gpt-4o-mini": "gpt-4o",
    "gpt-4o": "gpt-4o",
    "gpt-3.5-turbo": "gpt-4o",
}

# Cost per 1K tokens (input, output) - approximate as of late 2024
MODEL_COSTS = {
    "gpt-4o": (0.0025, 0.01),  # $2.50/$10.00 per 1M tokens
    "gpt-4o-mini": (0.00015, 0.0006),  # $0.15/$0.60 per 1M tokens
    "gpt-4-turbo": (0.01, 0.03),  # $10.00/$30.00 per 1M tokens
    "gpt-3.5-turbo": (0.0005, 0.0015),  # $0.50/$1.50 per 1M tokens
    "text-embedding-3-small": (0.00002, 0.0),  # $0.02 per 1M tokens (input only)
}


# =============================================================================
# Tracing Infrastructure
# =============================================================================

@dataclass
class LLMCallTrace:
    """Trace data for a single LLM call."""
    
    call_id: str
    timestamp: str
    node_name: str
    model: str
    temperature: float
    prompt: str  # Compiled prompt (with placeholders filled)
    response: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_estimate: float
    duration_ms: float
    success: bool
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass 
class NodeTrace:
    """Trace data for a single node execution."""
    
    trace_id: str
    timestamp: str
    node_name: str
    state_on_entry: dict[str, Any]
    state_on_exit: dict[str, Any] | None = None
    llm_calls: list[LLMCallTrace] = field(default_factory=list)
    duration_ms: float = 0.0
    success: bool = True
    error: str | None = None
    is_interrupt: bool = False  # True if node paused for user input


class TraceContext:
    """Thread-local context for tracing."""
    
    def __init__(self):
        self.run_id: str | None = None
        self.run_start: datetime | None = None
        self.traces: list[NodeTrace] = []
        self.current_node_trace: NodeTrace | None = None
        self.total_cost: float = 0.0
        self.total_tokens: int = 0
    
    def reset(self):
        """Reset for a new run."""
        self.run_id = str(uuid.uuid4())[:8]
        self.run_start = datetime.now()
        self.traces = []
        self.current_node_trace = None
        self.total_cost = 0.0
        self.total_tokens = 0


# Global trace context
_trace_context = TraceContext()


def is_tracing_enabled() -> bool:
    """Check if local tracing is enabled via PD3R_TRACING config."""
    from src.constants import TRACING
    return TRACING


def get_trace_context() -> TraceContext:
    """Get the current trace context."""
    return _trace_context


def start_run_trace() -> str:
    """Start tracing for a new run.
    
    Returns:
        Run ID for this trace session
    """
    _trace_context.reset()
    return _trace_context.run_id


def traced_node(func: Callable) -> Callable:
    """Decorator to wrap a LangGraph node function with tracing.

    Supports both sync and async node functions. LangGraph handles
    async nodes natively via ``await``, so async nodes should be
    registered directly (no sync wrapper or ``run_async`` bridge).

    Usage:
        @traced_node
        def my_sync_node(state: AgentState) -> dict:
            ...

        @traced_node
        async def my_async_node(state: AgentState) -> dict:
            ...

    Args:
        func: Node function to wrap (sync or async)

    Returns:
        Wrapped function with tracing (preserves sync/async nature)
    """
    if asyncio.iscoroutinefunction(func):
        @wraps(func)
        async def async_wrapper(state: dict[str, Any]) -> dict[str, Any]:
            node_name = func.__name__

            with trace_node(node_name, state) as trace:
                result = await func(state)

                # Record state on exit
                if trace and result:
                    finalize_node_trace(result)

                return result

        return async_wrapper
    else:
        @wraps(func)
        def wrapper(state: dict[str, Any]) -> dict[str, Any]:
            node_name = func.__name__

            with trace_node(node_name, state) as trace:
                result = func(state)

                # Record state on exit
                if trace and result:
                    finalize_node_trace(result)

                return result

        return wrapper


@contextmanager
def trace_node(node_name: str, state: dict[str, Any]) -> Generator[NodeTrace | None, None, None]:
    """Context manager for tracing a node execution.
    
    Args:
        node_name: Name of the node being traced
        state: State dictionary on entry
        
    Yields:
        NodeTrace object if tracing enabled, None otherwise
    """
    if not is_tracing_enabled():
        yield None
        return
    
    # Sanitize state (remove API keys if present)
    safe_state = _sanitize_state(state)
    
    trace = NodeTrace(
        trace_id=str(uuid.uuid4())[:8],
        timestamp=datetime.now().isoformat(),
        node_name=node_name,
        state_on_entry=safe_state,
    )
    _trace_context.current_node_trace = trace
    start_time = time.perf_counter()
    
    try:
        yield trace
    except Exception as e:
        # Check if this is a LangGraph interrupt (not a real error)
        # LangGraph wraps interrupts in various ways - check multiple patterns
        is_interrupt = False
        
        # Direct Interrupt instance
        if isinstance(e, Interrupt):
            is_interrupt = True
        # Exception wrapping an Interrupt in args
        elif hasattr(e, 'args') and e.args:
            first_arg = e.args[0]
            if isinstance(first_arg, Interrupt):
                is_interrupt = True
            # Tuple of Interrupts (common pattern)
            elif isinstance(first_arg, tuple) and first_arg and isinstance(first_arg[0], Interrupt):
                is_interrupt = True
        # Check string representation as fallback
        if not is_interrupt and 'Interrupt(' in str(e):
            is_interrupt = True
        
        if is_interrupt:
            trace.is_interrupt = True
            # Interrupts are expected - mark as success but note the interrupt
            trace.success = False  # Keep false for filtering, but is_interrupt=True clarifies
            trace.error = None  # Don't log interrupt as error
        else:
            trace.success = False
            trace.error = str(e)
        raise
    finally:
        trace.duration_ms = (time.perf_counter() - start_time) * 1000
        _trace_context.traces.append(trace)
        _trace_context.current_node_trace = None
        # Write incrementally after each node completes
        _append_node_trace(trace)


def trace_llm_call(
    node_name: str,
    model: str,
    temperature: float,
    prompt: str,
    response: str,
    input_tokens: int,
    output_tokens: int,
    duration_ms: float,
    success: bool = True,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> LLMCallTrace | None:
    """Record an LLM call trace.
    
    Args:
        node_name: Name of the calling node
        model: Model name used
        temperature: Temperature setting
        prompt: The compiled prompt sent to LLM
        response: The LLM response
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        duration_ms: Call duration in milliseconds
        success: Whether the call succeeded
        error: Error message if failed
        metadata: Additional metadata
        
    Returns:
        LLMCallTrace if tracing enabled, None otherwise
    """
    if not is_tracing_enabled():
        return None
    
    # Calculate cost
    total_tokens = input_tokens + output_tokens
    cost = _estimate_cost(model, input_tokens, output_tokens)
    
    # Sanitize prompt (remove any API keys)
    safe_prompt = _sanitize_prompt(prompt)
    
    trace = LLMCallTrace(
        call_id=str(uuid.uuid4())[:8],
        timestamp=datetime.now().isoformat(),
        node_name=node_name,
        model=model,
        temperature=temperature,
        prompt=safe_prompt,
        response=response,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cost_estimate=cost,
        duration_ms=duration_ms,
        success=success,
        error=error,
        metadata=metadata or {},
    )
    
    # Add to current node trace if exists
    if _trace_context.current_node_trace:
        _trace_context.current_node_trace.llm_calls.append(trace)
    
    # Update totals
    _trace_context.total_cost += cost
    _trace_context.total_tokens += total_tokens
    
    return trace


def finalize_node_trace(state_on_exit: dict[str, Any]) -> None:
    """Record the state on exit for current node trace.
    
    Args:
        state_on_exit: State dictionary after node execution
    """
    if not is_tracing_enabled():
        return
    
    if _trace_context.current_node_trace:
        _trace_context.current_node_trace.state_on_exit = _sanitize_state(state_on_exit)


def _get_trace_file_paths(output_dir: str = "output/logs") -> tuple[Path, Path]:
    """Get the file paths for trace logs.
    
    Returns:
        Tuple of (jsonl_path, readable_path)
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    timestamp = _trace_context.run_start.strftime("%Y%m%d_%H%M%S") if _trace_context.run_start else "unknown"
    base_name = f"{timestamp}_{_trace_context.run_id}"
    
    jsonl_path = output_path / f"{base_name}.jsonl"
    readable_path = output_path / f"{base_name}_readable.log"
    
    return jsonl_path, readable_path


def _append_node_trace(trace: NodeTrace, output_dir: str = "output/logs") -> None:
    """Append a single node trace to the log files incrementally.
    
    This is called after each node completes, ensuring traces are saved
    even if the run is interrupted (e.g., Ctrl+C).
    
    Args:
        trace: The completed node trace to append
        output_dir: Directory for log files
    """
    if not is_tracing_enabled():
        return
    
    jsonl_path, readable_path = _get_trace_file_paths(output_dir)
    
    # Append to JSONL
    record = {
        "event": "node_execution",
        "trace_id": trace.trace_id,
        "timestamp": trace.timestamp,
        "node_name": trace.node_name,
        "state_on_entry": trace.state_on_entry,
        "state_on_exit": trace.state_on_exit,
        "llm_calls": [
            {
                "call_id": call.call_id,
                "model": call.model,
                "temperature": call.temperature,
                "prompt": call.prompt[:500] + "..." if len(call.prompt) > 500 else call.prompt,
                "response": call.response[:500] + "..." if len(call.response) > 500 else call.response,
                "input_tokens": call.input_tokens,
                "output_tokens": call.output_tokens,
                "cost_estimate": round(call.cost_estimate, 6),
                "duration_ms": round(call.duration_ms, 2),
                "success": call.success,
                "error": call.error,
            }
            for call in trace.llm_calls
        ],
        "duration_ms": round(trace.duration_ms, 2),
        "success": trace.success,
        "is_interrupt": trace.is_interrupt,
        "error": trace.error,
    }
    
    with open(jsonl_path, "a") as f:
        f.write(json.dumps(record) + "\n")
    
    # Append to readable log - skip interrupt nodes for cleaner output
    if trace.is_interrupt:
        # Just write a minimal note for interrupts
        with open(readable_path, "a") as f:
            f.write(f"\n⏸️  INTERRUPT: {trace.node_name} (awaiting user input)\n")
        return
    
    with open(readable_path, "a") as f:
        f.write("\n" + "─" * 40 + "\n")
        f.write(f"NODE: {trace.node_name}\n")
        f.write("─" * 40 + "\n")
        f.write(f"Time: {trace.timestamp}\n")
        f.write(f"Duration: {trace.duration_ms:.2f}ms\n")
        f.write(f"Success: {trace.success}\n")
        if trace.error:
            f.write(f"Error: {trace.error}\n")
        
        # State summary
        if trace.state_on_entry:
            f.write("\n--- State on Entry ---\n")
            for key, value in trace.state_on_entry.items():
                f.write(f"  {key}: {_format_state_value(value)}\n")
        
        if trace.state_on_exit:
            f.write("\n--- State on Exit ---\n")
            for key, value in trace.state_on_exit.items():
                f.write(f"  {key}: {_format_state_value(value)}\n")
        
        # LLM calls
        for i, call in enumerate(trace.llm_calls, 1):
            f.write(f"\n--- LLM Call {i} ---\n")
            f.write(f"Model: {call.model} (temp={call.temperature})\n")
            f.write(f"Tokens: {call.input_tokens} in / {call.output_tokens} out\n")
            f.write(f"Cost: ${call.cost_estimate:.6f}\n")
            f.write(f"Duration: {call.duration_ms:.2f}ms\n")
            f.write(f"\nPrompt:\n  {call.prompt[:1000]}{'...' if len(call.prompt) > 1000 else ''}\n")
            f.write(f"\nResponse:\n  {call.response[:1000]}{'...' if len(call.response) > 1000 else ''}\n")


def _format_state_value(value: Any) -> str:
    """Format a state value for readable output."""
    if isinstance(value, list):
        return f"[...{len(value)} items...]"
    elif isinstance(value, dict):
        return f"{{...{len(value)} keys...}}"
    elif isinstance(value, str) and len(value) > 100:
        return f'"{value[:100]}..."'
    return str(value)


def save_trace_log(output_dir: str = "output/logs") -> tuple[str, str] | None:
    """Finalize the trace log files with summary information.
    
    Node traces are written incrementally during execution via _append_node_trace.
    This function writes the final summary and prepends header info.
    
    Writes two files:
    - <run_id>.jsonl: Machine-readable JSONL trace (summary + node traces)
    - <run_id>_readable.log: Human-readable formatted log
    
    Args:
        output_dir: Directory to save logs
        
    Returns:
        Tuple of (jsonl_path, readable_path) or None if tracing disabled
    """
    if not is_tracing_enabled():
        return None
    
    # If no traces, nothing to save
    if not _trace_context.traces:
        return None
    
    jsonl_path, readable_path = _get_trace_file_paths(output_dir)
    
    # Read existing incremental JSONL content if any
    existing_jsonl_content = ""
    if jsonl_path.exists():
        with open(jsonl_path, "r") as f:
            existing_jsonl_content = f.read()
    
    # Write summary as first line, then existing content
    summary = {
        "event": "run_summary",
        "run_id": _trace_context.run_id,
        "start_time": _trace_context.run_start.isoformat() if _trace_context.run_start else None,
        "total_cost": round(_trace_context.total_cost, 6),
        "total_tokens": _trace_context.total_tokens,
        "num_nodes": len(_trace_context.traces),
        "num_llm_calls": sum(len(t.llm_calls) for t in _trace_context.traces),
    }
    
    with open(jsonl_path, "w") as f:
        f.write(json.dumps(summary) + "\n")
        f.write(existing_jsonl_content)
    
    # Prepend header to readable log
    existing_readable_content = ""
    if readable_path.exists():
        with open(readable_path, "r") as f:
            existing_readable_content = f.read()
    
    with open(readable_path, "w") as f:
        f.write("=" * 80 + "\n")
        f.write(f"PD3r TRACE LOG - Run {_trace_context.run_id}\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Start Time: {_trace_context.run_start}\n")
        f.write(f"Total Cost: ${_trace_context.total_cost:.6f}\n")
        f.write(f"Total Tokens: {_trace_context.total_tokens:,}\n")
        f.write(f"Nodes Executed: {len(_trace_context.traces)}\n")
        f.write(f"LLM Calls: {sum(len(t.llm_calls) for t in _trace_context.traces)}\n")
        f.write("\n" + "=" * 80 + "\n")
        f.write(existing_readable_content)
    
    return str(jsonl_path), str(readable_path)


def _sanitize_state(state: dict[str, Any]) -> dict[str, Any]:
    """Remove sensitive data from state for tracing and make JSON-serializable.
    
    Args:
        state: State dictionary to sanitize
        
    Returns:
        Sanitized copy of state that is JSON-serializable
    """
    sensitive_keys = {"api_key", "token", "secret", "password", "credential"}
    
    def sanitize_value(key: str, value: Any) -> Any:
        key_lower = key.lower()
        if any(s in key_lower for s in sensitive_keys):
            return "[REDACTED]"
        
        # Handle LangChain message objects
        if hasattr(value, "content") and hasattr(value, "type"):
            # It's a Message object (AIMessage, HumanMessage, etc.)
            return {
                "type": getattr(value, "type", "unknown"),
                "content": str(value.content)[:500] + ("..." if len(str(value.content)) > 500 else ""),
            }
        
        # Handle Pydantic models
        if hasattr(value, "model_dump"):
            return sanitize_value(key, value.model_dump())
        
        if isinstance(value, dict):
            return {k: sanitize_value(k, v) for k, v in value.items()}
        if isinstance(value, list):
            return [sanitize_value(key, v) for v in value]
        
        # Handle other non-serializable types
        if not isinstance(value, (str, int, float, bool, type(None))):
            return str(value)[:200]
        
        return value
    
    return {k: sanitize_value(k, v) for k, v in state.items()}


def _sanitize_prompt(prompt: str) -> str:
    """Remove API keys from prompt strings.
    
    Args:
        prompt: Prompt string to sanitize
        
    Returns:
        Sanitized prompt
    """
    import re
    # Remove anything that looks like an API key
    # Pattern: sk-... or key-... followed by alphanumerics
    sanitized = re.sub(r'(sk|key|token|api)[_-]?[a-zA-Z0-9]{20,}', '[REDACTED]', prompt, flags=re.IGNORECASE)
    return sanitized


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost for an LLM call.
    
    Args:
        model: Model name
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        
    Returns:
        Estimated cost in USD
    """
    costs = MODEL_COSTS.get(model, MODEL_COSTS.get("gpt-4o", (0.0025, 0.01)))
    input_cost = (input_tokens / 1000) * costs[0]
    output_cost = (output_tokens / 1000) * costs[1]
    return input_cost + output_cost


def _format_state(state: dict[str, Any]) -> str:
    """Format state dict for human-readable log.
    
    Args:
        state: State dictionary
        
    Returns:
        Formatted string
    """
    lines = []
    for key, value in state.items():
        if key == "messages":
            lines.append(f"  messages: [{len(value)} messages]")
        elif isinstance(value, dict) and len(str(value)) > 100:
            lines.append(f"  {key}: {{...{len(value)} keys...}}")
        elif isinstance(value, list) and len(str(value)) > 100:
            lines.append(f"  {key}: [...{len(value)} items...]")
        else:
            lines.append(f"  {key}: {value}")
    return "\n".join(lines) + "\n"


def _indent(text: str, prefix: str) -> str:
    """Indent all lines of text with prefix."""
    return "\n".join(prefix + line for line in text.split("\n"))


# =============================================================================
# Retry Logic
# =============================================================================

def exponential_backoff_retry(
    max_retries: int = MAX_RETRIES,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
):
    """Decorator for exponential backoff retry on retryable exceptions.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds (doubled each retry)
        max_delay: Maximum delay between retries
        
    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    # Convert common LLM errors to our exceptions
                    exc = _convert_llm_exception(e)
                    
                    if not is_retryable(exc):
                        raise exc from e
                    
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                        await asyncio.sleep(delay)
            
            raise LLMRetryExhaustedError(
                message=f"Failed after {max_retries} attempts",
                attempts=max_retries,
                last_error=last_exception,
            )
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    exc = _convert_llm_exception(e)
                    
                    if not is_retryable(exc):
                        raise exc from e
                    
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                        time.sleep(delay)
            
            raise LLMRetryExhaustedError(
                message=f"Failed after {max_retries} attempts",
                attempts=max_retries,
                last_error=last_exception,
            )
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def _convert_llm_exception(e: Exception) -> Exception:
    """Convert common LLM provider exceptions to PD3r exceptions.
    
    Args:
        e: Original exception
        
    Returns:
        Converted PD3r exception
    """
    error_str = str(e).lower()
    error_type = type(e).__name__.lower()
    
    if "rate" in error_str or "ratelimit" in error_type:
        return LLMRateLimitError(str(e))
    elif "timeout" in error_str or "timeout" in error_type:
        return LLMTimeoutError(str(e))
    elif "connect" in error_str or "connection" in error_type:
        return LLMConnectionError(str(e))
    elif "json" in error_str or "parse" in error_str or "validation" in error_type:
        return LLMResponseError(str(e))
    
    # Return as-is if not recognized
    return e


# =============================================================================
# LLM Client Factory
# =============================================================================

def get_chat_model(
    model: str | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
) -> ChatOpenAI:
    """Get a configured ChatOpenAI instance.

    Args:
        model: Model name (defaults to OPENAI_DEFAULT_MODEL or gpt-4o)
        temperature: Temperature for generation (0.0 for deterministic)

    Returns:
        Configured ChatOpenAI instance
    """
    return ChatOpenAI(
        model=model or DEFAULT_MODEL,
        temperature=temperature,
        max_retries=MAX_RETRIES,
        timeout=TIMEOUT,
    )


def get_rewrite_model(base_model: str | None = None) -> ChatOpenAI:
    """Get an escalated model for rewrite attempts.

    Rewrite attempts use:
    - Escalated model (if available in MODEL_ESCALATION_MAP)
    - Lower temperature for more focused output
    - Same retry/timeout configuration

    Args:
        base_model: The original model used. If provided, attempts to escalate.

    Returns:
        ChatOpenAI configured for rewrite attempts
    """
    if base_model:
        escalated = MODEL_ESCALATION_MAP.get(base_model, REWRITE_MODEL)
    else:
        escalated = REWRITE_MODEL

    return ChatOpenAI(
        model=escalated,
        temperature=REWRITE_TEMPERATURE,
        max_retries=MAX_RETRIES,
        timeout=TIMEOUT,
    )


def get_model_for_attempt(
    attempt_number: int,
    base_model: str | None = None,
) -> tuple[ChatOpenAI, str]:
    """Get the appropriate model based on attempt number.

    First attempt uses default model and temperature.
    Subsequent attempts (rewrites) use escalated model and lower temperature.

    Args:
        attempt_number: Which attempt this is (1 = first, 2+ = rewrite)
        base_model: Optional base model to use/escalate from

    Returns:
        Tuple of (ChatOpenAI instance, model name used)
    """
    if attempt_number <= 1:
        model_name = base_model or DEFAULT_MODEL
        llm = get_chat_model(model=model_name, temperature=DEFAULT_TEMPERATURE)
    else:
        llm = get_rewrite_model(base_model)
        model_name = llm.model_name

    return llm, model_name


def get_structured_llm(
    schema: type[T],
    model: str | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
):
    """Get an LLM configured for structured output.

    Args:
        schema: Pydantic model class for output structure
        model: Model name (defaults to OPENAI_DEFAULT_MODEL or gpt-4o)
        temperature: Temperature for generation

    Returns:
        LLM bound to produce structured output matching schema
    """
    llm = get_chat_model(model=model, temperature=temperature)
    # Use function_calling method for schemas with Any types
    # (OpenAI's native structured output requires strict schema types)
    return llm.with_structured_output(schema, method="function_calling")


# =============================================================================
# Traced LLM Call Wrapper
# =============================================================================

async def traced_llm_call(
    llm: ChatOpenAI,
    prompt: str,
    node_name: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Execute an LLM call with tracing.
    
    Args:
        llm: ChatOpenAI instance
        prompt: Prompt to send
        node_name: Name of calling node
        metadata: Additional metadata for trace
        
    Returns:
        Tuple of (response_content, usage_info)
    """
    start_time = time.perf_counter()
    response_content = ""
    input_tokens = 0
    output_tokens = 0
    success = True
    error = None
    
    try:
        response = await llm.ainvoke(prompt)
        response_content = response.content if hasattr(response, "content") else str(response)
        
        # Extract token usage if available
        if hasattr(response, "response_metadata"):
            usage = response.response_metadata.get("token_usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
        
    except Exception as e:
        success = False
        error = str(e)
        raise
    
    finally:
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        # Record trace
        trace_llm_call(
            node_name=node_name,
            model=llm.model_name,
            temperature=llm.temperature,
            prompt=prompt,
            response=response_content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            success=success,
            error=error,
            metadata=metadata,
        )
    
    usage_info = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cost_estimate": _estimate_cost(llm.model_name, input_tokens, output_tokens),
    }
    
    return response_content, usage_info


async def traced_structured_llm_call(
    llm: ChatOpenAI,
    prompt: str,
    output_schema: type[T],
    node_name: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[T, dict[str, Any]]:
    """Execute an LLM call with structured output and tracing.
    
    Args:
        llm: ChatOpenAI instance
        prompt: Prompt to send
        output_schema: Pydantic model class for structured output
        node_name: Name of calling node
        metadata: Additional metadata for trace
        
    Returns:
        Tuple of (parsed_result, usage_info)
    """
    start_time = time.perf_counter()
    response_content = ""
    input_tokens = 0
    output_tokens = 0
    success = True
    error = None
    result = None
    
    try:
        # Use function_calling method for schemas with Any types
        # (OpenAI's native structured output requires strict schema types)
        structured_llm = llm.with_structured_output(output_schema, method="function_calling")
        result = await structured_llm.ainvoke(prompt)
        response_content = result.model_dump_json() if hasattr(result, "model_dump_json") else str(result)
        
        # Token usage not directly available from structured output, estimate from prompt
        # This is approximate - actual tokens depend on response size
        input_tokens = len(prompt) // 4  # Rough estimate
        output_tokens = len(response_content) // 4
        
    except Exception as e:
        success = False
        error = str(e)
        raise
    
    finally:
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        trace_llm_call(
            node_name=node_name,
            model=llm.model_name,
            temperature=llm.temperature,
            prompt=prompt,
            response=response_content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            success=success,
            error=error,
            metadata=metadata,
        )
    
    usage_info = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cost_estimate": _estimate_cost(llm.model_name, input_tokens, output_tokens),
    }
    
    return result, usage_info


def traced_llm_call_sync(
    llm: ChatOpenAI,
    prompt: str,
    node_name: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Synchronous version of traced_llm_call.
    
    Args:
        llm: ChatOpenAI instance
        prompt: Prompt to send
        node_name: Name of calling node
        metadata: Additional metadata for trace
        
    Returns:
        Tuple of (response_content, usage_info)
    """
    start_time = time.perf_counter()
    response_content = ""
    input_tokens = 0
    output_tokens = 0
    success = True
    error = None
    
    try:
        response = llm.invoke(prompt)
        response_content = response.content if hasattr(response, "content") else str(response)
        
        if hasattr(response, "response_metadata"):
            usage = response.response_metadata.get("token_usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
        
    except Exception as e:
        success = False
        error = str(e)
        raise
    
    finally:
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        trace_llm_call(
            node_name=node_name,
            model=llm.model_name,
            temperature=llm.temperature,
            prompt=prompt,
            response=response_content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            success=success,
            error=error,
            metadata=metadata,
        )
    
    usage_info = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cost_estimate": _estimate_cost(llm.model_name, input_tokens, output_tokens),
    }
    
    return response_content, usage_info
