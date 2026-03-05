"""Unit tests for draft and requirements models."""

import pytest

from src.models.draft import (
    DRAFT_ELEMENT_NAMES,
    DraftAttempt,
    DraftElement,
    QACheckResult,
    QAReview,
    create_all_draft_elements,
    create_draft_element,
)
from src.models.requirements import DraftRequirement, DraftRequirements


class TestQACheckResult:
    """Tests for QACheckResult model."""

    def test_create_passed_check(self):
        """Test creating a passed check result."""
        result = QACheckResult(
            requirement_id="req_1",
            passed=True,
            explanation="Requirement clearly met",
            severity="critical",
        )
        assert result.passed is True
        assert result.suggestion is None

    def test_create_failed_check(self):
        """Test creating a failed check result."""
        result = QACheckResult(
            requirement_id="req_1",
            passed=False,
            explanation="Missing required content",
            severity="critical",
            suggestion="Add the required statement",
        )
        assert result.passed is False
        assert result.suggestion is not None


class TestQAReview:
    """Tests for QAReview model."""

    def test_create_passing_review(self):
        """Test creating a passing QA review."""
        review = QAReview(
            passes=True,
            check_results=[
                QACheckResult(
                    requirement_id="req_1", passed=True, explanation="Good"
                ),
                QACheckResult(
                    requirement_id="req_2", passed=True, explanation="Good"
                ),
            ],
            overall_feedback="Excellent draft",
        )
        assert review.passes is True
        assert review.passed_count == 2
        assert review.failed_count == 0
        assert len(review.critical_failures) == 0

    def test_create_failing_review(self):
        """Test creating a failing QA review."""
        review = QAReview(
            passes=False,
            check_results=[
                QACheckResult(
                    requirement_id="req_1", passed=True, explanation="Good"
                ),
                QACheckResult(
                    requirement_id="req_2",
                    passed=False,
                    explanation="Missing",
                    severity="critical",
                ),
            ],
            overall_feedback="Needs work",
            needs_rewrite=True,
            suggested_revisions=["Add missing content"],
        )
        assert review.passes is False
        assert review.passed_count == 1
        assert review.failed_count == 1
        assert len(review.critical_failures) == 1
        assert review.needs_rewrite is True

    def test_warnings_property(self):
        """Test warnings property."""
        review = QAReview(
            passes=False,
            check_results=[
                QACheckResult(
                    requirement_id="req_1",
                    passed=False,
                    explanation="Warning",
                    severity="warning",
                ),
            ],
            overall_feedback="Minor issues",
        )
        assert len(review.warnings) == 1
        assert len(review.critical_failures) == 0


class TestDraftElement:
    """Tests for DraftElement model."""

    def test_create_element(self):
        """Test creating a draft element."""
        element = create_draft_element("introduction")
        assert element.name == "introduction"
        assert element.display_name == "Introduction"
        assert element.status == "pending"
        assert element.content == ""

    def test_update_content(self):
        """Test updating element content."""
        element = create_draft_element("introduction")
        element.update_content("This is the introduction.", is_rewrite=False)
        assert element.content == "This is the introduction."
        assert element.status == "drafted"
        assert element.revision_count == 0  # Not a rewrite

    def test_update_content_rewrite(self):
        """Test updating content as a rewrite."""
        element = create_draft_element("introduction")
        element.update_content("First draft")
        element.update_content("Second draft", is_rewrite=True)
        assert element.revision_count == 1

    def test_can_rewrite(self):
        """Test can_rewrite property."""
        element = create_draft_element("introduction")
        assert element.can_rewrite is True

        element.update_content("First draft", is_rewrite=True)
        assert element.can_rewrite is False
        assert element.hit_rewrite_limit is True

    def test_apply_qa_review_passes(self):
        """Test applying a passing QA review."""
        element = create_draft_element("introduction")
        element.update_content("Good draft")

        review = QAReview(
            passes=True,
            check_results=[
                QACheckResult(requirement_id="req_1", passed=True, explanation="Good")
            ],
            overall_feedback="Approved",
        )
        element.apply_qa_review(review)

        assert element.status == "qa_passed"
        assert element.qa_review is not None
        assert len(element.qa_history) == 1

    def test_apply_qa_review_fails(self):
        """Test applying a failing QA review."""
        element = create_draft_element("introduction")
        element.update_content("Bad draft")

        review = QAReview(
            passes=False,
            check_results=[
                QACheckResult(
                    requirement_id="req_1", passed=False, explanation="Missing"
                )
            ],
            overall_feedback="Needs work",
            needs_rewrite=True,
            suggested_revisions=["Add content"],
        )
        element.apply_qa_review(review)

        assert element.status == "needs_revision"
        assert element.can_rewrite is True  # First attempt

    def test_qa_history_preserved(self):
        """Test that QA history is preserved across reviews."""
        element = create_draft_element("introduction")

        # First review
        review1 = QAReview(
            passes=False, check_results=[], overall_feedback="First review"
        )
        element.apply_qa_review(review1)

        # Second review
        review2 = QAReview(
            passes=True, check_results=[], overall_feedback="Second review"
        )
        element.apply_qa_review(review2)

        assert len(element.qa_history) == 2

    def test_approve(self):
        """Test approving an element."""
        element = create_draft_element("introduction")
        element.update_content("Draft content")
        element.approve()
        assert element.status == "approved"

    def test_request_revision(self):
        """Test requesting revision with feedback."""
        element = create_draft_element("introduction")
        element.update_content("Draft content")
        element.request_revision("Please add more detail")
        assert element.status == "needs_revision"
        assert element.feedback == "Please add more detail"


class TestDraftElementConstants:
    """Tests for draft element constants."""

    def test_draft_element_names(self):
        """Test that required element names are defined."""
        assert "introduction" in DRAFT_ELEMENT_NAMES
        assert "major_duties" in DRAFT_ELEMENT_NAMES
        assert "factor_1_knowledge" in DRAFT_ELEMENT_NAMES

    def test_create_all_draft_elements(self):
        """Test creating all draft elements."""
        elements = create_all_draft_elements()
        assert len(elements) == len(DRAFT_ELEMENT_NAMES)
        assert all(isinstance(e, DraftElement) for e in elements)


class TestDraftRequirement:
    """Tests for DraftRequirement model."""

    def test_create_keyword_requirement(self):
        """Test creating a keyword-based requirement."""
        req = DraftRequirement(
            id="req_1",
            description="Must include position title",
            element_name="introduction",
            check_type="keyword",
            keywords=["position", "title"],
            is_critical=True,
            source="Structure Requirements",
        )
        assert req.id == "req_1"
        assert req.check_type == "keyword"
        assert req.is_critical is True

    def test_create_weight_requirement(self):
        """Test creating a weight-based requirement."""
        req = DraftRequirement(
            id="duty_weight_1",
            description="Section must be 20-35%",
            element_name="major_duties",
            check_type="weight",
            is_critical=True,
            source="Duty Template",
            min_weight=20,
            max_weight=35,
        )
        assert req.min_weight == 20
        assert req.max_weight == 35


class TestDraftRequirements:
    """Tests for DraftRequirements collection model."""

    @pytest.fixture
    def sample_requirements(self):
        """Create sample requirements for testing."""
        return DraftRequirements(
            requirements=[
                DraftRequirement(
                    id="req_1",
                    description="Critical requirement for intro",
                    element_name="introduction",
                    check_type="keyword",
                    is_critical=True,
                    source="FES",
                ),
                DraftRequirement(
                    id="req_2",
                    description="Advisory requirement for intro",
                    element_name="introduction",
                    check_type="semantic",
                    is_critical=False,
                    source="Structure",
                ),
                DraftRequirement(
                    id="req_3",
                    description="Duty section requirement",
                    element_name="major_duties",
                    check_type="weight",
                    is_critical=True,
                    source="Duty Template 2210-13",
                ),
            ],
            series="2210",
            grade=13,
            is_supervisor=False,
        )

    def test_get_requirements_for_element(self, sample_requirements):
        """Test filtering requirements by element."""
        intro_reqs = sample_requirements.get_requirements_for_element("introduction")
        assert len(intro_reqs) == 2

        duty_reqs = sample_requirements.get_requirements_for_element("major_duties")
        assert len(duty_reqs) == 1

    def test_get_critical_requirements(self, sample_requirements):
        """Test getting critical requirements."""
        critical = sample_requirements.get_critical_requirements()
        assert len(critical) == 2
        assert all(r.is_critical for r in critical)

    def test_get_advisory_requirements(self, sample_requirements):
        """Test getting advisory requirements."""
        advisory = sample_requirements.get_advisory_requirements()
        assert len(advisory) == 1
        assert all(not r.is_critical for r in advisory)

    def test_counts(self, sample_requirements):
        """Test requirement counts."""
        assert sample_requirements.total_count == 3
        assert sample_requirements.critical_count == 2

    def test_add_requirement(self, sample_requirements):
        """Test adding a requirement."""
        new_req = DraftRequirement(
            id="req_4",
            description="New requirement",
            element_name="factor_1_knowledge",
            check_type="semantic",
            is_critical=True,
            source="FES Factor 1",
        )
        sample_requirements.add_requirement(new_req)
        assert sample_requirements.total_count == 4

    def test_to_summary(self, sample_requirements):
        """Test generating summary."""
        summary = sample_requirements.to_summary()
        assert "GS-13" in summary
        assert "2210" in summary
        assert "3" in summary  # Total count


class TestDraftAttempt:
    """Tests for DraftAttempt model."""

    def test_create_draft_attempt(self):
        """Test creating a draft attempt."""
        attempt = DraftAttempt(
            content="Draft content here",
            qa_passed=False,
            qa_feedback="Needs more detail",
            qa_failures=["Missing supervisory statement", "Grade level unclear"],
            user_feedback=None,
            rewrite_reason="qa_failure",
        )
        assert attempt.content == "Draft content here"
        assert attempt.qa_passed is False
        assert len(attempt.qa_failures) == 2
        assert attempt.rewrite_reason == "qa_failure"

    def test_draft_attempt_with_user_feedback(self):
        """Test draft attempt with user feedback."""
        attempt = DraftAttempt(
            content="Draft v2",
            qa_passed=True,
            qa_feedback="Looks good",
            qa_failures=[],
            user_feedback="Please make it shorter",
            rewrite_reason="user_revision",
        )
        assert attempt.user_feedback == "Please make it shorter"
        assert attempt.rewrite_reason == "user_revision"

    def test_draft_attempt_defaults(self):
        """Test draft attempt default values."""
        attempt = DraftAttempt(content="Simple draft")
        assert attempt.qa_passed is False
        assert attempt.qa_feedback == ""
        assert attempt.qa_failures == []
        assert attempt.user_feedback is None
        assert attempt.rewrite_reason is None


class TestDraftElementRewriteContext:
    """Tests for DraftElement rewrite context functionality."""

    @pytest.fixture
    def element_with_history(self):
        """Create element with draft history."""
        element = DraftElement(
            name="major_duties",
            display_name="Major Duties",
            order=1,
            content="Current draft content",
            status="drafted",
            draft_history=[
                DraftAttempt(
                    content="First attempt",
                    qa_passed=False,
                    qa_feedback="Missing key details",
                    qa_failures=["Must include supervisory duties"],
                    rewrite_reason="qa_failure",
                ),
            ],
            rewrite_reason="qa_failure",
        )
        return element

    def test_is_rewrite_property_false(self):
        """Test is_rewrite is False for new elements."""
        element = DraftElement(
            name="major_duties", display_name="Major Duties", order=1
        )
        assert element.is_rewrite is False

    def test_is_rewrite_property_true(self, element_with_history):
        """Test is_rewrite is True when history exists."""
        assert element_with_history.is_rewrite is True

    def test_attempt_number_first_attempt(self):
        """Test attempt_number is 1 for new elements."""
        element = DraftElement(
            name="major_duties", display_name="Major Duties", order=1
        )
        assert element.attempt_number == 1

    def test_attempt_number_with_history(self, element_with_history):
        """Test attempt_number reflects history length."""
        assert element_with_history.attempt_number == 2

    def test_save_to_history_qa_failure(self):
        """Test save_to_history captures QA failure context."""
        element = DraftElement(
            name="major_duties",
            display_name="Major Duties",
            order=1,
            content="Original content",
            qa_review=QAReview(
                passes=False,
                check_results=[
                    QACheckResult(
                        requirement_id="req_1",
                        passed=False,
                        explanation="Missing supervisory statement",
                        severity="critical",
                    ),
                ],
                overall_feedback="Needs work",
            ),
        )
        element.save_to_history(reason="qa_failure")

        assert len(element.draft_history) == 1
        attempt = element.draft_history[0]
        assert attempt.content == "Original content"
        assert attempt.qa_passed is False
        assert "req_1" in attempt.qa_failures[0]
        assert element.rewrite_reason == "qa_failure"

    def test_save_to_history_user_revision(self):
        """Test save_to_history captures user revision context."""
        element = DraftElement(
            name="major_duties",
            display_name="Major Duties",
            order=1,
            content="Original content",
            feedback="Please be more specific about grades",
        )
        element.save_to_history(reason="user_revision")

        assert len(element.draft_history) == 1
        attempt = element.draft_history[0]
        assert attempt.user_feedback == "Please be more specific about grades"
        assert element.rewrite_reason == "user_revision"

    def test_get_rewrite_context_structure(self, element_with_history):
        """Test get_rewrite_context returns expected structure."""
        context = element_with_history.get_rewrite_context()

        assert "attempt_number" in context
        assert "previous_drafts" in context
        assert "failure_reasons" in context
        assert "has_user_feedback" in context
        assert "latest_user_feedback" in context
        assert "rewrite_reason" in context

    def test_get_rewrite_context_attempt_number(self, element_with_history):
        """Test get_rewrite_context returns correct attempt number."""
        context = element_with_history.get_rewrite_context()
        assert context["attempt_number"] == 2

    def test_get_rewrite_context_failure_reasons(self, element_with_history):
        """Test get_rewrite_context aggregates failure reasons."""
        context = element_with_history.get_rewrite_context()
        assert len(context["failure_reasons"]) > 0
        assert "[QA]" in context["failure_reasons"][0]

    def test_get_rewrite_context_with_user_feedback(self):
        """Test get_rewrite_context includes user feedback."""
        element = DraftElement(
            name="major_duties",
            display_name="Major Duties",
            order=1,
            content="Draft v2",
            draft_history=[
                DraftAttempt(
                    content="First draft",
                    user_feedback="Too long",
                    rewrite_reason="user_revision",
                ),
            ],
            feedback="Still needs work",
        )
        context = element.get_rewrite_context()

        assert context["has_user_feedback"] is True
        assert context["latest_user_feedback"] == "Still needs work"
        assert any("[User]" in r for r in context["failure_reasons"])

    def test_get_rewrite_context_multiple_attempts(self):
        """Test get_rewrite_context with multiple previous attempts."""
        element = DraftElement(
            name="major_duties",
            display_name="Major Duties",
            order=1,
            content="Draft v3",
            draft_history=[
                DraftAttempt(
                    content="First draft",
                    qa_passed=False,
                    qa_failures=["Missing scope"],
                ),
                DraftAttempt(
                    content="Second draft",
                    qa_passed=False,
                    qa_failures=["Still missing scope"],
                    user_feedback="Better but needs work",
                ),
            ],
        )
        context = element.get_rewrite_context()

        assert context["attempt_number"] == 3
        assert len(context["previous_drafts"]) == 2
        assert len(context["failure_reasons"]) >= 2


class TestModelEscalation:
    """Tests for model escalation utilities."""

    def test_rewrite_constants(self):
        """Test rewrite constants are defined."""
        from src.utils import (
            MODEL_ESCALATION_MAP,
            REWRITE_MODEL,
            REWRITE_TEMPERATURE,
        )

        assert REWRITE_MODEL == "gpt-4o"
        assert REWRITE_TEMPERATURE == 0.1
        assert "gpt-4o-mini" in MODEL_ESCALATION_MAP

    def test_get_rewrite_model_returns_llm(self):
        """Test get_rewrite_model returns a ChatOpenAI instance."""
        from unittest.mock import patch

        from src.utils import get_rewrite_model

        # Mock ChatOpenAI to avoid API key requirement
        with patch("src.utils.llm.ChatOpenAI") as mock_chat:
            mock_chat.return_value = "mock_llm"
            result = get_rewrite_model()
            mock_chat.assert_called_once()
            # Verify correct arguments passed
            call_kwargs = mock_chat.call_args.kwargs
            assert call_kwargs["model"] == "gpt-4o"
            assert call_kwargs["temperature"] == 0.1

    def test_get_rewrite_model_escalates_mini(self):
        """Test get_rewrite_model escalates gpt-4o-mini to gpt-4o."""
        from unittest.mock import patch

        from src.utils import get_rewrite_model

        with patch("src.utils.llm.ChatOpenAI") as mock_chat:
            mock_chat.return_value = "mock_llm"
            get_rewrite_model(base_model="gpt-4o-mini")
            call_kwargs = mock_chat.call_args.kwargs
            assert call_kwargs["model"] == "gpt-4o"

    def test_get_model_for_attempt_first(self):
        """Test first attempt uses default settings."""
        from unittest.mock import patch

        from src.utils import DEFAULT_MODEL, DEFAULT_TEMPERATURE, get_model_for_attempt

        with patch("src.utils.llm.ChatOpenAI") as mock_chat:
            mock_chat.return_value.model_name = DEFAULT_MODEL
            llm, model_name = get_model_for_attempt(1)
            call_kwargs = mock_chat.call_args.kwargs
            assert call_kwargs["model"] == DEFAULT_MODEL
            assert call_kwargs["temperature"] == DEFAULT_TEMPERATURE

    def test_get_model_for_attempt_rewrite(self):
        """Test rewrite attempts use escalated settings."""
        from unittest.mock import patch

        from src.utils import REWRITE_MODEL, REWRITE_TEMPERATURE, get_model_for_attempt

        with patch("src.utils.llm.ChatOpenAI") as mock_chat:
            mock_chat.return_value.model_name = REWRITE_MODEL
            llm, model_name = get_model_for_attempt(2)
            call_kwargs = mock_chat.call_args.kwargs
            assert call_kwargs["model"] == REWRITE_MODEL
            assert call_kwargs["temperature"] == REWRITE_TEMPERATURE
