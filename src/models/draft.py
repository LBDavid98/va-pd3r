"""Draft models for position description generation.

Models for tracking draft elements, QA reviews, and the drafting workflow.
"""

import hashlib
from typing import Literal

from pydantic import BaseModel, Field


class DraftAttempt(BaseModel):
    """Record of a single draft attempt for history tracking."""

    content: str = Field(default="", description="The draft content from this attempt (empty after compaction)")
    qa_passed: bool = Field(default=False, description="Whether this attempt passed QA")
    qa_feedback: str = Field(default="", description="QA feedback for this attempt")
    qa_failures: list[str] = Field(
        default_factory=list, description="Specific requirement failures from QA"
    )
    user_feedback: str | None = Field(
        default=None, description="User feedback if revision was requested"
    )
    rewrite_reason: Literal["qa_failure", "user_revision", None] = Field(
        default=None, description="Why a rewrite was triggered"
    )


class QACheckResult(BaseModel):
    """
    Result of checking a single requirement against draft content.
    """

    requirement_id: str = Field(..., description="ID of the requirement checked")
    passed: bool = Field(..., description="Whether the requirement was met")
    explanation: str = Field(
        ..., description="Why the check passed or failed"
    )
    severity: Literal["critical", "warning", "info"] = Field(
        default="critical", description="Severity if check failed"
    )
    suggestion: str | None = Field(
        default=None, description="Suggested fix if check failed"
    )


class QAReview(BaseModel):
    """
    Complete QA review of a draft element.
    """

    passes: bool = Field(..., description="Whether the element passes QA overall")
    check_results: list[QACheckResult] = Field(
        default_factory=list, description="Individual check results"
    )
    overall_feedback: str = Field(
        default="", description="General feedback about the draft"
    )
    needs_rewrite: bool = Field(
        default=False, description="Whether element needs complete rewrite"
    )
    suggested_revisions: list[str] = Field(
        default_factory=list, description="Specific revisions needed"
    )

    @property
    def critical_failures(self) -> list[QACheckResult]:
        """Get critical check failures."""
        return [
            r for r in self.check_results
            if not r.passed and r.severity == "critical"
        ]

    @property
    def warnings(self) -> list[QACheckResult]:
        """Get warning-level failures."""
        return [
            r for r in self.check_results
            if not r.passed and r.severity == "warning"
        ]

    @property
    def passed_count(self) -> int:
        """Count of passed checks."""
        return sum(1 for r in self.check_results if r.passed)

    @property
    def failed_count(self) -> int:
        """Count of failed checks."""
        return sum(1 for r in self.check_results if not r.passed)


class DraftElement(BaseModel):
    """
    A single element/section of the position description draft.

    Tracks the content, status, QA results, and revision history
    for one section of the PD.
    """

    name: str = Field(
        ..., description="Element name (e.g., 'introduction', 'factor_1', 'major_duties')"
    )
    display_name: str = Field(
        ..., description="Human-readable name for display"
    )
    content: str = Field(
        default="", description="Current draft content"
    )
    status: Literal["pending", "drafted", "qa_passed", "approved", "needs_revision"] = Field(
        default="pending", description="Current status of the element"
    )
    feedback: str = Field(
        default="", description="User feedback requesting changes"
    )
    revision_count: int = Field(
        default=0, description="Number of times this element has been revised (max 1 rewrite)"
    )

    # Rewrite context tracking (4.3.D)
    draft_history: list[DraftAttempt] = Field(
        default_factory=list, description="History of all draft attempts with QA/feedback"
    )
    rewrite_reason: Literal["qa_failure", "user_revision", None] = Field(
        default=None, description="Reason for current rewrite (if any)"
    )

    # Execution dependencies
    prerequisites: list[str] = Field(
        default_factory=list,
        description="Element names that must be drafted before this element starts",
    )

    # QA tracking
    qa_review: QAReview | None = Field(
        default=None, description="Most recent QA review"
    )
    qa_history: list[dict] = Field(
        default_factory=list, description="History of all QA reviews for this element"
    )
    requirements_checked: int = Field(
        default=0, description="Number of requirements checked"
    )
    requirements_passed: int = Field(
        default=0, description="Number of requirements that passed"
    )
    requirements_failed: int = Field(
        default=0, description="Number of requirements that failed"
    )
    qa_notes: list[str] = Field(
        default_factory=list, description="Notes from QA review"
    )
    # Content hash for QA caching (Issue 1.4)
    last_qa_content_hash: str | None = Field(
        default=None,
        description="Hash of content at last QA run, for skip-if-unchanged optimization",
    )

    @property
    def is_complete(self) -> bool:
        """Check if element is complete (approved or QA passed)."""
        return self.status in ("approved", "qa_passed")

    @property
    def needs_work(self) -> bool:
        """Check if element needs more work."""
        return self.status in ("pending", "needs_revision")

    @property
    def qa_passed(self) -> bool:
        """Check if element passed QA."""
        return self.qa_review is not None and self.qa_review.passes

    @property
    def can_rewrite(self) -> bool:
        """Check if element can be rewritten (limit 1 rewrite)."""
        return self.revision_count < 1

    @property
    def hit_rewrite_limit(self) -> bool:
        """Check if element has hit the rewrite limit."""
        return self.revision_count >= 1

    def compute_content_hash(self) -> str:
        """Compute hash of current content for QA caching."""
        return hashlib.sha256(self.content.encode()).hexdigest()[:16]

    def qa_content_unchanged(self) -> bool:
        """Check if content hasn't changed since last QA."""
        if not self.last_qa_content_hash or not self.qa_review:
            return False
        return self.compute_content_hash() == self.last_qa_content_hash

    @property
    def is_rewrite(self) -> bool:
        """Check if the next generation would be a rewrite."""
        return self.revision_count > 0 or self.rewrite_reason is not None

    @property
    def attempt_number(self) -> int:
        """Get the current attempt number (1 for first, 2 for rewrite)."""
        return len(self.draft_history) + 1

    def prerequisites_met(self, completed_elements: set[str]) -> bool:
        """Return True if all prerequisites are satisfied."""
        return all(req in completed_elements for req in self.prerequisites)

    def save_to_history(
        self,
        reason: Literal["qa_failure", "user_revision", None] = None,
    ) -> None:
        """
        Save current draft to history before rewrite.

        Call this BEFORE generating new content to preserve
        the previous attempt with its QA results and feedback.

        Args:
            reason: Why the rewrite is being triggered
        """
        if not self.content:
            return  # Nothing to save

        # Build QA failure list from current review
        qa_failures = []
        if self.qa_review:
            for check in self.qa_review.check_results:
                if not check.passed:
                    qa_failures.append(f"{check.requirement_id}: {check.explanation}")

        attempt = DraftAttempt(
            content=self.content,
            qa_passed=self.qa_review.passes if self.qa_review else False,
            qa_feedback=self.qa_review.overall_feedback if self.qa_review else "",
            qa_failures=qa_failures,
            user_feedback=self.feedback or None,
            rewrite_reason=reason,
        )
        self.draft_history.append(attempt)
        self.rewrite_reason = reason

    def get_rewrite_context(self) -> dict:
        """
        Build context dict for rewrite template.

        Returns context with:
        - attempt_number: Which attempt this is (2+)
        - previous_drafts: List of previous attempt records
        - failure_reasons: Aggregated list of why rewrites were needed
        - has_user_feedback: Whether user provided feedback
        - latest_user_feedback: Most recent user feedback

        Returns:
            Dict of rewrite context for templates
        """
        failure_reasons = []
        latest_user_feedback = None

        for attempt in self.draft_history:
            # Add QA failures
            for failure in attempt.qa_failures:
                failure_reasons.append(f"[QA] {failure}")

            # Add user feedback
            if attempt.user_feedback:
                failure_reasons.append(f"[User] {attempt.user_feedback}")
                latest_user_feedback = attempt.user_feedback

        # Also include current feedback if not yet in history
        if self.feedback and self.feedback != latest_user_feedback:
            failure_reasons.append(f"[User] {self.feedback}")
            latest_user_feedback = self.feedback

        return {
            "attempt_number": self.attempt_number,
            "previous_drafts": [a.model_dump() for a in self.draft_history],
            "failure_reasons": failure_reasons,
            "has_user_feedback": latest_user_feedback is not None,
            "latest_user_feedback": latest_user_feedback,
            "rewrite_reason": self.rewrite_reason,
        }

    def update_content(self, new_content: str, is_rewrite: bool = False) -> None:
        """Update content and track revision."""
        self.content = new_content
        self.status = "drafted"
        if is_rewrite:
            self.revision_count += 1
            # Clear rewrite reason after successful update
            self.rewrite_reason = None
        # Clear user feedback after generation so it doesn't leak into
        # future auto-rewrite cycles (stale feedback prevention).
        self.feedback = ""

    def apply_qa_review(self, review: QAReview) -> None:
        """Apply QA review results and save to history."""
        # Save content hash for caching (Issue 1.4)
        self.last_qa_content_hash = self.compute_content_hash()
        
        # Save to history first
        self.qa_history.append(review.model_dump())
        
        # Update current review
        self.qa_review = review
        self.requirements_checked = len(review.check_results)
        self.requirements_passed = review.passed_count
        self.requirements_failed = review.failed_count

        if review.passes:
            self.status = "qa_passed"
        elif review.needs_rewrite and self.can_rewrite:
            self.status = "needs_revision"
            self.qa_notes = review.suggested_revisions
        else:
            # Failed but can't rewrite - still mark as needing review
            # but user will have to decide
            self.status = "needs_revision"
            self.qa_notes = review.suggested_revisions

    def approve(self) -> None:
        """Mark element as approved by user."""
        self.status = "approved"

    def request_revision(self, feedback: str) -> None:
        """Request revision with feedback."""
        self.feedback = feedback
        self.status = "needs_revision"


# Constants for draft elements
DRAFT_ELEMENT_NAMES: list[str] = [
    "introduction",
    "background",
    "major_duties",
    "factor_1_knowledge",
    "factor_2_supervisory_controls",
    "factor_3_guidelines",
    "factor_4_complexity",
    "factor_5_scope_effect",
    "factor_6_7_contacts",
    "factor_8_physical_demands",
    "factor_9_work_environment",
    "other_significant_factors",
]

# Supervisory draft elements (OPM General Schedule Supervisory Guide factors)
# Only included when is_supervisor=True
SUPERVISORY_DRAFT_ELEMENT_NAMES: list[str] = [
    "supervisory_factor_1_program_scope",
    "supervisory_factor_2_organizational_setting",
    "supervisory_factor_3_authority",
    "supervisory_factor_4_contacts",
    "supervisory_factor_5_work_directed",
    "supervisory_factor_6_other_conditions",
]

# Display names for each element
DRAFT_ELEMENT_DISPLAY_NAMES: dict[str, str] = {
    "introduction": "Introduction",
    "background": "Background",
    "major_duties": "Major Duties and Responsibilities",
    "factor_1_knowledge": "Factor 1: Knowledge Required",
    "factor_2_supervisory_controls": "Factor 2: Supervisory Controls",
    "factor_3_guidelines": "Factor 3: Guidelines",
    "factor_4_complexity": "Factor 4: Complexity",
    "factor_5_scope_effect": "Factor 5: Scope and Effect",
    "factor_6_7_contacts": "Factor 6/7: Personal Contacts and Purpose of Contacts",
    "factor_8_physical_demands": "Factor 8: Physical Demands",
    "factor_9_work_environment": "Factor 9: Work Environment",
    "other_significant_factors": "Other Significant Factors",
    # Supervisory factors (GSSG)
    "supervisory_factor_1_program_scope": "Supervisory Factor 1: Program Scope and Effect",
    "supervisory_factor_2_organizational_setting": "Supervisory Factor 2: Organizational Setting",
    "supervisory_factor_3_authority": "Supervisory Factor 3: Supervisory and Managerial Authority",
    "supervisory_factor_4_contacts": "Supervisory Factor 4: Personal Contacts",
    "supervisory_factor_5_work_directed": "Supervisory Factor 5: Difficulty of Work Directed",
    "supervisory_factor_6_other_conditions": "Supervisory Factor 6: Other Conditions",
}

# Prerequisite graph for draft elements. Elements become eligible once all listed
# prerequisites have reached at least the "drafted" state.
DRAFT_ELEMENT_PREREQUISITES: dict[str, list[str]] = {
    "introduction": [],
    "background": ["introduction"],
    "major_duties": ["introduction", "background"],
    "factor_1_knowledge": ["introduction", "major_duties"],
    "factor_2_supervisory_controls": ["introduction", "major_duties"],
    "factor_3_guidelines": ["introduction", "major_duties"],
    "factor_4_complexity": ["introduction", "major_duties"],
    "factor_5_scope_effect": ["introduction", "major_duties"],
    "factor_6_7_contacts": ["introduction", "major_duties"],
    "factor_8_physical_demands": ["introduction", "major_duties"],
    "factor_9_work_environment": ["introduction", "major_duties"],
    "other_significant_factors": ["introduction", "major_duties"],
    # Supervisory factors depend on major_duties being complete
    "supervisory_factor_1_program_scope": ["introduction", "major_duties"],
    "supervisory_factor_2_organizational_setting": ["introduction", "major_duties"],
    "supervisory_factor_3_authority": ["introduction", "major_duties"],
    "supervisory_factor_4_contacts": ["introduction", "major_duties"],
    "supervisory_factor_5_work_directed": ["introduction", "major_duties"],
    "supervisory_factor_6_other_conditions": ["introduction", "major_duties"],
}

# Primary FES factors (1-5) - each gets its own section
PRIMARY_FES_FACTORS: list[int] = [1, 2, 3, 4, 5]

# Other significant factors (6-9) - each gets its own section/element
OTHER_SIGNIFICANT_FACTORS: list[int] = [6, 7, 8, 9]


def create_draft_element(name: str) -> DraftElement:
    """Create a draft element with appropriate display name."""
    display_name = DRAFT_ELEMENT_DISPLAY_NAMES.get(name, name.replace("_", " ").title())
    return DraftElement(
        name=name,
        display_name=display_name,
        prerequisites=DRAFT_ELEMENT_PREREQUISITES.get(name, []),
    )


def create_all_draft_elements(is_supervisor: bool = False) -> list[DraftElement]:
    """Create all draft elements for a PD.

    Args:
        is_supervisor: If True, includes supervisory factors from OPM GSSG

    Returns:
        List of DraftElement objects for the PD
    """
    element_names = list(DRAFT_ELEMENT_NAMES)

    # Add supervisory elements if position is supervisory
    if is_supervisor:
        element_names.extend(SUPERVISORY_DRAFT_ELEMENT_NAMES)

    return [create_draft_element(name) for name in element_names]


def _prereq_satisfied_names(draft_elements: list[DraftElement | dict]) -> set[str]:
    """Names of elements that satisfy prerequisites for dependents.

    We treat any element that has reached at least the drafted state as satisfying
    its prerequisites, allowing dependent sections to start in parallel.
    """
    satisfied: set[str] = set()
    for elem in draft_elements:
        element = DraftElement.model_validate(elem) if isinstance(elem, dict) else elem
        if element.status in {"drafted", "qa_passed", "approved"}:
            satisfied.add(element.name)
    return satisfied


def find_ready_indices(draft_elements: list[dict]) -> list[int]:
    """Return all indices whose prerequisites are met and need work/QA.

    Elements eligible if status is pending, needs_revision, or drafted.
    This allows already drafted sections (generated in a batch) to proceed to QA.
    """
    satisfied = _prereq_satisfied_names(draft_elements)
    ready: list[int] = []
    for idx, elem in enumerate(draft_elements):
        element = DraftElement.model_validate(elem)
        if element.status in {"pending", "needs_revision", "drafted"} and element.prerequisites_met(satisfied):
            ready.append(idx)
    return ready


def find_actionable_indices(draft_elements: list[dict]) -> list[int]:
    """Return all indices that need attention: generation, QA, or user approval.

    Includes statuses: pending, needs_revision, drafted, qa_passed.
    Use this in advance/handle nodes where qa_passed elements should not be skipped.
    For generation-only filtering, use find_ready_indices() instead.
    """
    satisfied = _prereq_satisfied_names(draft_elements)
    actionable: list[int] = []
    for idx, elem in enumerate(draft_elements):
        element = DraftElement.model_validate(elem)
        if element.status in {"pending", "needs_revision", "drafted", "qa_passed"} and element.prerequisites_met(satisfied):
            actionable.append(idx)
    return actionable


def find_next_ready_index(draft_elements: list[dict]) -> int | None:
    """Find the first actionable index (includes qa_passed elements)."""
    actionable = find_actionable_indices(draft_elements)
    return actionable[0] if actionable else None
