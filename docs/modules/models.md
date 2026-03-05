# Models Reference

> **Last Updated**: 2026-01-16  
> **Module Path**: `src/models/`

---

## Overview

Pydantic v2 models define all data contracts for PD3r. These are the **source of truth** — code adapts to models, never the reverse.

---

## Model Files

| File | Models | Purpose |
|------|--------|---------|
| `state.py` | `AgentState` | LangGraph state container (TypedDict) |
| `interview.py` | `InterviewElement`, `InterviewData` | Interview data collection with metadata |
| `intent.py` | `IntentClassification`, `FieldMapping`, `Question` | Intent classification and extraction |
| `position.py` | `PositionDescription` | Core PD output model |
| `fes.py` | `FESFactorLevel`, `FESEvaluation` | FES factor evaluation models |
| `duties.py` | `DutySection`, `SeriesDutyTemplate` | Series-specific duty requirements |
| `requirements.py` | `DraftRequirement`, `DraftRequirements` | QA requirements collection |
| `draft.py` | `DraftElement`, `QAReview`, `QACheckResult` | Draft element tracking and QA |

---

## Key Models

### `AgentState` (TypedDict)

LangGraph state container — uses TypedDict for reducer compatibility.

```python
class AgentState(TypedDict):
    # Message history (LangGraph managed)
    messages: Annotated[list, add_messages]
    
    # Conversation phase
    phase: Literal["init", "interview", "requirements", "drafting", "review", "complete"]
    
    # Interview tracking
    interview_data: Optional[dict]  # Serialized InterviewData
    current_field: Optional[str]
    missing_fields: list[str]
    fields_needing_confirmation: list[str]
    
    # Intent classification
    last_intent: Optional[str]  # Primary intent for routing
    intent_classification: Optional[object]  # Full IntentClassification for structured details
    pending_question: Optional[str]
    
    # FES & Drafting
    fes_evaluation: Optional[dict]
    draft_requirements: Optional[dict]
    draft_elements: list[dict]
    current_element_index: int
    current_element_name: Optional[str]
    
    # Control flow
    should_end: bool
    next_prompt: str
```

### `InterviewData`

Collected interview responses with per-element metadata tracking.

```python
class InterviewData(BaseModel):
    position_title: InterviewElement[str]
    organization: InterviewElement[list[str]]
    organization_hierarchy: InterviewElement[list[str]]
    series: InterviewElement[str]
    grade: InterviewElement[str]
    is_supervisor: InterviewElement[bool]  # Supervisory status flag
    num_supervised: InterviewElement[int]  # Conditional on is_supervisor
    percent_supervising: InterviewElement[int]  # Conditional on is_supervisor
    reports_to: InterviewElement[str]
    daily_activities: InterviewElement[list[str]]
    major_duties: InterviewElement[list[str]]
    qualifications: InterviewElement[list[str]]
    work_environment: InterviewElement[str]
    physical_demands: InterviewElement[str]
    travel_required: InterviewElement[bool]
    travel_percentage: InterviewElement[int]
```

### `IntentClassification`

LLM structured output for analyzing user messages.

```python
class IntentClassification(BaseModel):
    primary_intent: IntentType  # provide_information, ask_question, confirm, reject, etc.
    secondary_intents: list[IntentType]
    confidence: float
    field_mappings: list[FieldMapping]  # Extracted field values
    questions: list[Question]  # Questions asked
    modifications: list[FieldModification]  # Change requests
```

### `FESEvaluation`

Complete FES evaluation with all 9 factors.

```python
class FESEvaluation(BaseModel):
    grade: str  # "GS-13"
    grade_num: int
    
    # Primary factors (1-5) - separate PD sections
    factor_1_knowledge: FESFactorLevel | None
    factor_2_supervisory_controls: FESFactorLevel | None
    factor_3_guidelines: FESFactorLevel | None
    factor_4_complexity: FESFactorLevel | None
    factor_5_scope_and_effect: FESFactorLevel | None
    
    # Other factors (6-9) - combined section
    factor_6_personal_contacts: FESFactorLevel | None
    factor_7_purpose_of_contacts: FESFactorLevel | None
    factor_8_physical_demands: FESFactorLevel | None
    factor_9_work_environment: FESFactorLevel | None
    
    total_points: int
```

### `DraftElement`

Tracks a single PD section through drafting and QA with prerequisite-aware parallel execution.

```python
class DraftElement(BaseModel):
    name: str
    display_name: str
    content: str
    status: Literal["pending", "drafted", "qa_passed", "approved", "needs_revision"]
    feedback: str
    revision_count: int  # Max 1 rewrite
    qa_review: QAReview | None
    qa_history: list[dict]
    prerequisites: list[str]  # Element names that must be drafted first
```

Helpers: `find_ready_indices(draft_elements)` returns all elements whose prerequisites are met and need work/QA; used for parallel generation and QA.

---

## Draft Elements (8 total)

```python
DRAFT_ELEMENT_NAMES = [
    "introduction",
    "major_duties",
    "factor_1_knowledge",
    "factor_2_supervisory_controls",
    "factor_3_guidelines",
    "factor_4_complexity",
    "factor_5_scope_and_effect",
    "other_significant_factors",
]
```

---

## Validation Rules

- All string fields are stripped and non-empty
- Grade must match pattern `GS-\d{1,2}`
- Series must be 4-digit OPM code
- Revision count limited to 1 per element

---

## Testing

```bash
poetry run pytest tests/test_unit_models.py tests/test_unit_*.py -v
```
