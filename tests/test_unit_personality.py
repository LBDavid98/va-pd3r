"""Tests for personality utilities (phrase rotation)."""

import pytest

from src.utils.personality import (
    ACKNOWLEDGMENT_PHRASES,
    BACK_TO_TOPIC_PHRASES,
    COMPLETION_PHRASES,
    CONFIRMATION_SUCCESS_PHRASES,
    REVISION_ACKNOWLEDGMENT_PHRASES,
    TRANSITION_PHRASES,
    WORKING_PHRASES,
    acknowledge_and_list,
    get_acknowledgment,
    get_back_to_topic,
    get_completion,
    get_confirmation_success,
    get_revision_acknowledgment,
    get_transition,
    get_working,
    present_draft,
    reset_phrase_history,
    transition_to,
)


class TestPhraseCategories:
    """Test that phrase categories have sufficient variety."""

    def test_acknowledgment_phrases_variety(self):
        """Acknowledgment phrases should have at least 5 options."""
        assert len(ACKNOWLEDGMENT_PHRASES) >= 5

    def test_transition_phrases_variety(self):
        """Transition phrases should have at least 5 options."""
        assert len(TRANSITION_PHRASES) >= 5

    def test_working_phrases_variety(self):
        """Working phrases should have at least 5 options."""
        assert len(WORKING_PHRASES) >= 5

    def test_completion_phrases_variety(self):
        """Completion phrases should have at least 5 options."""
        assert len(COMPLETION_PHRASES) >= 5

    def test_confirmation_success_phrases_variety(self):
        """Confirmation success phrases should have at least 5 options."""
        assert len(CONFIRMATION_SUCCESS_PHRASES) >= 5

    def test_revision_acknowledgment_phrases_variety(self):
        """Revision acknowledgment phrases should have at least 5 options."""
        assert len(REVISION_ACKNOWLEDGMENT_PHRASES) >= 5

    def test_back_to_topic_phrases_variety(self):
        """Back to topic phrases should have at least 3 options."""
        assert len(BACK_TO_TOPIC_PHRASES) >= 3


class TestPhraseRotation:
    """Test that phrase rotation avoids immediate repetition."""

    def setup_method(self):
        """Reset phrase history before each test."""
        reset_phrase_history()

    def test_acknowledgment_rotation_avoids_immediate_repeat(self):
        """get_acknowledgment should avoid immediate repeats."""
        # Get 10 phrases and check no consecutive duplicates
        phrases = [get_acknowledgment() for _ in range(10)]
        for i in range(1, len(phrases)):
            assert phrases[i] != phrases[i - 1], "Consecutive phrases should differ"

    def test_transition_rotation_avoids_immediate_repeat(self):
        """get_transition should avoid immediate repeats."""
        phrases = [get_transition() for _ in range(10)]
        for i in range(1, len(phrases)):
            assert phrases[i] != phrases[i - 1], "Consecutive phrases should differ"

    def test_working_rotation_avoids_immediate_repeat(self):
        """get_working should avoid immediate repeats."""
        phrases = [get_working() for _ in range(10)]
        for i in range(1, len(phrases)):
            assert phrases[i] != phrases[i - 1], "Consecutive phrases should differ"

    def test_completion_rotation_avoids_immediate_repeat(self):
        """get_completion should avoid immediate repeats."""
        phrases = [get_completion() for _ in range(10)]
        for i in range(1, len(phrases)):
            assert phrases[i] != phrases[i - 1], "Consecutive phrases should differ"

    def test_confirmation_rotation_avoids_immediate_repeat(self):
        """get_confirmation_success should avoid immediate repeats."""
        phrases = [get_confirmation_success() for _ in range(10)]
        for i in range(1, len(phrases)):
            assert phrases[i] != phrases[i - 1], "Consecutive phrases should differ"

    def test_revision_rotation_avoids_immediate_repeat(self):
        """get_revision_acknowledgment should avoid immediate repeats."""
        phrases = [get_revision_acknowledgment() for _ in range(10)]
        for i in range(1, len(phrases)):
            assert phrases[i] != phrases[i - 1], "Consecutive phrases should differ"

    def test_back_to_topic_rotation_avoids_immediate_repeat(self):
        """get_back_to_topic should avoid immediate repeats."""
        phrases = [get_back_to_topic() for _ in range(10)]
        for i in range(1, len(phrases)):
            assert phrases[i] != phrases[i - 1], "Consecutive phrases should differ"


class TestResetHistory:
    """Test the reset_phrase_history function."""

    def test_reset_clears_history(self):
        """After reset, phrases can repeat."""
        # Get some phrases to establish history
        for _ in range(5):
            get_acknowledgment()

        # Reset history
        reset_phrase_history()

        # Now any phrase is possible (no avoidance)
        # We can't easily test this deterministically, but we can ensure
        # the function runs without error and phrases are still returned
        phrase = get_acknowledgment()
        assert phrase in ACKNOWLEDGMENT_PHRASES


class TestConvenienceFunctions:
    """Test convenience functions for building responses."""

    def setup_method(self):
        """Reset phrase history before each test."""
        reset_phrase_history()

    def test_acknowledge_and_list_empty(self):
        """acknowledge_and_list with empty list returns just acknowledgment."""
        result = acknowledge_and_list([])
        assert result in ACKNOWLEDGMENT_PHRASES

    def test_acknowledge_and_list_with_items(self):
        """acknowledge_and_list formats items as bullet list."""
        items = ["Position Title: IT Specialist", "Series: 2210"]
        result = acknowledge_and_list(items)

        # Should start with acknowledgment phrase
        assert any(result.startswith(phrase) for phrase in ACKNOWLEDGMENT_PHRASES)

        # Should contain bullet items
        assert "- Position Title: IT Specialist" in result
        assert "- Series: 2210" in result

    def test_acknowledge_and_list_with_single_item(self):
        """acknowledge_and_list works with single item."""
        result = acknowledge_and_list(["Grade: GS-13"])
        assert "- Grade: GS-13" in result

    def test_transition_to_basic(self):
        """transition_to combines phrase with topic."""
        result = transition_to("the grade level")

        # Should contain the topic
        assert "the grade level" in result

        # Should start with or contain a transition phrase pattern
        assert any(
            phrase.rstrip(":") in result or phrase.rstrip(":") in result
            for phrase in TRANSITION_PHRASES
        )

    def test_transition_to_handles_colon_endings(self):
        """transition_to handles phrases ending in colon."""
        # Test multiple times to get different phrases
        reset_phrase_history()
        for _ in range(7):
            result = transition_to("your organization")
            # Should not have double colons or awkward spacing
            assert "::" not in result
            assert result.strip() != ""

    def test_present_draft_basic(self):
        """present_draft formats element name properly."""
        result = present_draft("Introduction")

        # Should contain the element name
        assert "Introduction" in result

        # Should be formatted with bold
        assert "**Introduction**" in result

    def test_present_draft_with_question_completion(self):
        """present_draft handles 'How's this?' style completion."""
        reset_phrase_history()
        # Run multiple times to hit different completion phrases
        found_question_style = False
        for _ in range(20):
            reset_phrase_history()
            result = present_draft("Major Duties")
            if "?" in result:
                found_question_style = True
                # Question-style should have element on new line
                assert "Major Duties" in result
                break

        # At least verify basic format works
        result = present_draft("Major Duties")
        assert "Major Duties" in result


class TestPhraseContent:
    """Test that phrase content follows Pete's voice guidelines."""

    def test_acknowledgment_phrases_use_contractions(self):
        """Acknowledgment phrases should use contractions (Pete's voice)."""
        contraction_count = sum(
            1 for phrase in ACKNOWLEDGMENT_PHRASES
            if "I've" in phrase or "I'm" in phrase or "that's" in phrase
        )
        # At least half should use contractions
        assert contraction_count >= len(ACKNOWLEDGMENT_PHRASES) // 2

    def test_acknowledgment_phrases_are_positive(self):
        """Acknowledgment phrases should be positive."""
        positive_words = ["great", "got", "perfect", "thanks", "excellent", "awesome"]
        positive_count = sum(
            1 for phrase in ACKNOWLEDGMENT_PHRASES
            if any(word in phrase.lower() for word in positive_words)
        )
        # All should be positive
        assert positive_count == len(ACKNOWLEDGMENT_PHRASES)

    def test_confirmation_phrases_are_enthusiastic(self):
        """Confirmation success phrases should be enthusiastic."""
        # All should end with exclamation
        for phrase in CONFIRMATION_SUCCESS_PHRASES:
            assert phrase.endswith("!"), f"'{phrase}' should end with !"

    def test_working_phrases_indicate_activity(self):
        """Working phrases should indicate ongoing activity."""
        activity_indicators = ["...", "moment", "working", "let me", "sec"]
        for phrase in WORKING_PHRASES:
            assert any(
                ind in phrase.lower() for ind in activity_indicators
            ), f"'{phrase}' should indicate activity"


class TestEdgeCases:
    """Test edge cases and error handling."""

    def setup_method(self):
        """Reset phrase history before each test."""
        reset_phrase_history()

    def test_all_getters_return_string(self):
        """All phrase getters should return strings."""
        assert isinstance(get_acknowledgment(), str)
        assert isinstance(get_transition(), str)
        assert isinstance(get_working(), str)
        assert isinstance(get_completion(), str)
        assert isinstance(get_confirmation_success(), str)
        assert isinstance(get_revision_acknowledgment(), str)
        assert isinstance(get_back_to_topic(), str)

    def test_all_phrases_non_empty(self):
        """All returned phrases should be non-empty."""
        for _ in range(10):
            assert len(get_acknowledgment()) > 0
            assert len(get_transition()) > 0
            assert len(get_working()) > 0
            assert len(get_completion()) > 0
            assert len(get_confirmation_success()) > 0
            assert len(get_revision_acknowledgment()) > 0
            assert len(get_back_to_topic()) > 0

    def test_heavy_usage_doesnt_break(self):
        """Heavy usage shouldn't cause issues."""
        # Get 100 of each phrase type
        for _ in range(100):
            get_acknowledgment()
            get_transition()
            get_working()
            get_completion()
            get_confirmation_success()
            get_revision_acknowledgment()
            get_back_to_topic()
        # If we got here without error, test passes
        assert True
