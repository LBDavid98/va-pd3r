"""Tests for src/api/element_tracker.py — element change detection."""

import pytest
from src.api.element_tracker import ElementChangeTracker, _content_hash


class TestContentHash:
    def test_empty_string_returns_empty(self):
        assert _content_hash("") == ""

    def test_nonempty_returns_hex(self):
        h = _content_hash("hello world")
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)

    def test_same_input_same_hash(self):
        assert _content_hash("test") == _content_hash("test")

    def test_different_input_different_hash(self):
        assert _content_hash("aaa") != _content_hash("bbb")

    def test_long_content_hashed_fully(self):
        """Regression: old hash used len + first 50 chars, missing changes beyond 50."""
        base = "x" * 100
        changed = base[:60] + "Y" + base[61:]
        assert _content_hash(base) != _content_hash(changed)


class TestElementChangeTracker:
    def _elem(self, name="intro", status="pending", content="", qa_review=None):
        d = {"name": name, "status": status, "content": content, "display_name": name.title()}
        if qa_review is not None:
            d["qa_review"] = qa_review
        return d

    def test_no_changes_returns_empty(self):
        initial = [self._elem("intro", "pending", "Hello")]
        tracker = ElementChangeTracker(initial)
        changes = tracker.detect_changes([self._elem("intro", "pending", "Hello")])
        assert changes == []

    def test_status_change_detected(self):
        initial = [self._elem("intro", "pending", "Hello")]
        tracker = ElementChangeTracker(initial)
        changes = tracker.detect_changes([self._elem("intro", "qa_passed", "Hello")])
        assert len(changes) == 1
        assert changes[0].name == "intro"
        assert changes[0].status == "qa_passed"
        assert changes[0].content == "Hello"

    def test_content_change_detected(self):
        initial = [self._elem("intro", "qa_passed", "Version 1")]
        tracker = ElementChangeTracker(initial)
        changes = tracker.detect_changes([self._elem("intro", "qa_passed", "Version 2")])
        assert len(changes) == 1
        assert changes[0].content == "Version 2"

    def test_new_element_detected(self):
        tracker = ElementChangeTracker([])
        changes = tracker.detect_changes([self._elem("intro", "drafted", "Draft")])
        assert len(changes) == 1
        assert changes[0].name == "intro"

    def test_drafted_status_omits_content(self):
        """Pre-QA 'drafted' sends status-only update to prevent two-drafts flicker."""
        tracker = ElementChangeTracker([])
        changes = tracker.detect_changes([self._elem("intro", "drafted", "Draft text")])
        assert len(changes) == 1
        assert changes[0].status == "drafted"
        assert changes[0].content is None  # No content for drafted

    def test_qa_passed_includes_content(self):
        tracker = ElementChangeTracker([])
        changes = tracker.detect_changes([self._elem("intro", "qa_passed", "Final text")])
        assert len(changes) == 1
        assert changes[0].content == "Final text"

    def test_qa_review_transformed(self):
        qa = {
            "passes": True,
            "overall_feedback": "Good",
            "check_results": [
                {"requirement_id": "r1", "passed": True, "explanation": "OK", "severity": "critical"},
            ],
            "passed_count": 1,
            "failed_count": 0,
        }
        tracker = ElementChangeTracker([])
        changes = tracker.detect_changes([self._elem("intro", "qa_passed", "Text", qa_review=qa)])
        assert len(changes) == 1
        assert changes[0].qa_review is not None
        assert changes[0].qa_review["passes"] is True
        assert len(changes[0].qa_review["checks"]) == 1

    def test_no_qa_review_is_none(self):
        tracker = ElementChangeTracker([])
        changes = tracker.detect_changes([self._elem("intro", "qa_passed", "Text")])
        assert changes[0].qa_review is None

    def test_multiple_elements_only_changed_returned(self):
        initial = [
            self._elem("intro", "approved", "Intro text"),
            self._elem("duties", "pending", ""),
        ]
        tracker = ElementChangeTracker(initial)
        current = [
            self._elem("intro", "approved", "Intro text"),  # unchanged
            self._elem("duties", "drafted", "New duties"),   # changed
        ]
        changes = tracker.detect_changes(current)
        assert len(changes) == 1
        assert changes[0].name == "duties"

    def test_non_dict_elements_skipped(self):
        tracker = ElementChangeTracker([])
        changes = tracker.detect_changes(["not_a_dict", None, 42])
        assert changes == []

    def test_successive_calls_track_state(self):
        """Tracker remembers state across calls — second unchanged call returns empty."""
        tracker = ElementChangeTracker([])
        changes1 = tracker.detect_changes([self._elem("intro", "qa_passed", "V1")])
        assert len(changes1) == 1
        changes2 = tracker.detect_changes([self._elem("intro", "qa_passed", "V1")])
        assert changes2 == []
        changes3 = tracker.detect_changes([self._elem("intro", "approved", "V1")])
        assert len(changes3) == 1

    def test_to_dict_full_change(self):
        tracker = ElementChangeTracker([])
        changes = tracker.detect_changes([self._elem("intro", "qa_passed", "Content")])
        d = tracker.to_dict(changes[0])
        assert d["name"] == "intro"
        assert d["status"] == "qa_passed"
        assert d["content"] == "Content"
        assert d["display_name"] == "Intro"

    def test_to_dict_status_only(self):
        tracker = ElementChangeTracker([])
        changes = tracker.detect_changes([self._elem("intro", "drafted", "Content")])
        d = tracker.to_dict(changes[0])
        assert d["name"] == "intro"
        assert d["status"] == "drafted"
        assert "content" not in d  # status-only for drafted
