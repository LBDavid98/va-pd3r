"""Tests for structured element_action protocol — intent classification bypass."""

import re
import pytest

from src.nodes.intent_classification_node import (
    _ACTION_PREFIX_RE,
    _ACTION_INTENT_MAP,
    _classify_structured_action,
)


class TestActionPrefixRegex:
    """Test the structured action prefix pattern."""

    def test_approve_matches(self):
        m = _ACTION_PREFIX_RE.match("[ACTION:approve:introduction]")
        assert m is not None
        assert m.group(1) == "approve"
        assert m.group(2) == "introduction"
        assert m.group(3) is None

    def test_reject_matches(self):
        m = _ACTION_PREFIX_RE.match("[ACTION:reject:major_duties]")
        assert m is not None
        assert m.group(1) == "reject"
        assert m.group(2) == "major_duties"

    def test_regenerate_with_feedback(self):
        m = _ACTION_PREFIX_RE.match("[ACTION:regenerate:factor_1_knowledge] Make it more detailed")
        assert m is not None
        assert m.group(1) == "regenerate"
        assert m.group(2) == "factor_1_knowledge"
        assert m.group(3) == "Make it more detailed"

    def test_regenerate_multiline_feedback(self):
        m = _ACTION_PREFIX_RE.match("[ACTION:regenerate:introduction] Line 1\nLine 2")
        assert m is not None
        assert m.group(3) == "Line 1\nLine 2"

    def test_no_match_regular_text(self):
        assert _ACTION_PREFIX_RE.match("approve") is None
        assert _ACTION_PREFIX_RE.match("I approve this section") is None
        assert _ACTION_PREFIX_RE.match("[approve]") is None

    def test_no_match_malformed(self):
        assert _ACTION_PREFIX_RE.match("[ACTION:]") is None
        assert _ACTION_PREFIX_RE.match("[ACTION:approve]") is None  # no element


class TestClassifyStructuredAction:
    """Test the structured action → intent mapping."""

    def test_approve_maps_to_confirm(self):
        m = _ACTION_PREFIX_RE.match("[ACTION:approve:introduction]")
        result = _classify_structured_action(m)
        assert result["last_intent"] == "confirm"
        assert result["_structured_action"]["action"] == "approve"
        assert result["_structured_action"]["element"] == "introduction"

    def test_reject_maps_to_reject(self):
        m = _ACTION_PREFIX_RE.match("[ACTION:reject:introduction]")
        result = _classify_structured_action(m)
        assert result["last_intent"] == "reject"

    def test_regenerate_maps_to_modify_answer(self):
        m = _ACTION_PREFIX_RE.match("[ACTION:regenerate:introduction]")
        result = _classify_structured_action(m)
        assert result["last_intent"] == "modify_answer"

    def test_regenerate_with_feedback_includes_modification(self):
        m = _ACTION_PREFIX_RE.match("[ACTION:regenerate:introduction] Add more detail about duties")
        result = _classify_structured_action(m)
        assert result["last_intent"] == "modify_answer"
        assert result["_modification"]["field"] == "introduction"
        assert result["_modification"]["new_value"] == "Add more detail about duties"

    def test_regenerate_without_feedback_no_modification(self):
        m = _ACTION_PREFIX_RE.match("[ACTION:regenerate:introduction]")
        result = _classify_structured_action(m)
        assert "_modification" not in result

    def test_unknown_action_maps_to_unrecognized(self):
        m = _ACTION_PREFIX_RE.match("[ACTION:delete:introduction]")
        result = _classify_structured_action(m)
        assert result["last_intent"] == "unrecognized"

    def test_structured_action_metadata_preserved(self):
        m = _ACTION_PREFIX_RE.match("[ACTION:approve:factor_2_supervisory_controls]")
        result = _classify_structured_action(m)
        sa = result["_structured_action"]
        assert sa["action"] == "approve"
        assert sa["element"] == "factor_2_supervisory_controls"
        assert sa["feedback"] == ""

    def test_no_intent_classification_object(self):
        """Structured actions should NOT include full IntentClassification."""
        m = _ACTION_PREFIX_RE.match("[ACTION:approve:introduction]")
        result = _classify_structured_action(m)
        assert "intent_classification" not in result


class TestActionIntentMap:
    """Test the action→intent mapping is complete."""

    def test_all_actions_mapped(self):
        assert "approve" in _ACTION_INTENT_MAP
        assert "reject" in _ACTION_INTENT_MAP
        assert "regenerate" in _ACTION_INTENT_MAP

    def test_approve_is_confirm(self):
        assert _ACTION_INTENT_MAP["approve"] == "confirm"

    def test_reject_is_reject(self):
        assert _ACTION_INTENT_MAP["reject"] == "reject"

    def test_regenerate_is_modify_answer(self):
        assert _ACTION_INTENT_MAP["regenerate"] == "modify_answer"
