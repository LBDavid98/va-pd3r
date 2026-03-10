"""Element change detection for WebSocket streaming.

Tracks draft element state across graph streaming events and emits
change notifications only when status or content actually changes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from src.api.transforms import qa_review_to_summary


@dataclass
class ElementChange:
    """A detected change in a draft element."""

    name: str
    status: str
    display_name: str
    content: str | None = None
    qa_review: dict | None = None


def _content_hash(content: str) -> str:
    """Compute a stable hash of element content."""
    if not content:
        return ""
    return hashlib.sha256(content.encode()).hexdigest()[:16]


class ElementChangeTracker:
    """Detects draft element changes across graph streaming events.

    Initialized with the pre-stream element state (from checkpoint) so that
    the first streaming event (which echoes pre-update state) does not emit
    spurious change notifications.

    Usage::

        tracker = ElementChangeTracker(checkpoint_elements)
        for event in graph.astream(...):
            for change in tracker.detect_changes(event.get("draft_elements", [])):
                await on_element_update(change.to_dict())
    """

    def __init__(self, initial_elements: list[dict]) -> None:
        self._prev: dict[str, tuple[str, str]] = {}  # name → (status, content_hash)
        for elem in initial_elements:
            if isinstance(elem, dict):
                name = elem.get("name", "")
                status = elem.get("status", "")
                content = elem.get("content") or ""
                self._prev[name] = (status, _content_hash(content))

    def detect_changes(self, current_elements: list[dict]) -> list[ElementChange]:
        """Compare current elements against last-seen state.

        Returns a list of ElementChange objects for elements whose status
        or content has changed since the last call.

        For elements in "drafted" status (pre-QA), returns a status-only
        change (content=None) to prevent the "two drafts" flicker where
        pre-QA content is shown then replaced by a rewrite.
        """
        changes: list[ElementChange] = []

        for elem in current_elements:
            if not isinstance(elem, dict):
                continue

            name = elem.get("name", "")
            status = elem.get("status", "")
            content = elem.get("content") or ""
            c_hash = _content_hash(content)

            prev = self._prev.get(name)
            if prev is not None and prev == (status, c_hash):
                continue  # No change

            # Record new state
            self._prev[name] = (status, c_hash)

            display_name = elem.get("display_name", name)

            # Pre-QA "drafted" → status-only update (no content)
            if status == "drafted":
                changes.append(ElementChange(
                    name=name,
                    status=status,
                    display_name=display_name,
                ))
                continue

            # Full update with content and QA summary
            qa_summary = qa_review_to_summary(elem.get("qa_review"))
            changes.append(ElementChange(
                name=name,
                status=status,
                display_name=display_name,
                content=content,
                qa_review=qa_summary,
            ))

        return changes

    def to_dict(self, change: ElementChange) -> dict:
        """Convert an ElementChange to the WebSocket message shape."""
        d: dict[str, Any] = {
            "name": change.name,
            "status": change.status,
            "display_name": change.display_name,
        }
        if change.content is not None:
            d["content"] = change.content
        if change.qa_review is not None:
            d["qa_review"] = change.qa_review
        return d
