"""Async compatibility utilities for running async code from sync contexts.

Provides a consistent pattern for calling async functions from synchronous
node wrappers, handling both cases:
- Called from a sync context (no event loop) → asyncio.run()
- Called from an async context (event loop exists) → run in executor
"""

import asyncio
import concurrent.futures
from typing import Any, Callable, Coroutine


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async coroutine from a sync context, handling event loop conflicts.

    If no event loop is running, uses asyncio.run() directly.
    If an event loop is already running (e.g., called from async graph execution),
    submits the coroutine to a thread pool executor to avoid "cannot run nested
    event loop" errors.

    Args:
        coro: The coroutine to execute

    Returns:
        The result of the coroutine
    """
    try:
        asyncio.get_running_loop()
        # We're in an async context — run in executor to avoid nested loop
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        # No running loop — safe to use asyncio.run directly
        return asyncio.run(coro)
