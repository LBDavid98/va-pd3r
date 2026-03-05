# PD3r MVP Implementation Plan

> **Created**: 2026-01-14  
> **Status**: Draft  
> **Goal**: Implement conversational PD writing agent with human-in-the-loop flow

---

## Executive Summary

This plan delivers an MVP of **PD3r (Pete)**, a conversational agent that guides users through writing federal position descriptions. The agent uses LangGraph's `interrupt()` pattern for human-in-the-loop interactions and a state machine to track interview progress, draft generation, and revision cycles.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [State Model](#2-state-model)
3. [Node Specifications](#3-node-specifications)
4. [Graph Structure](#4-graph-structure)
5. [User Experience Flow](#5-user-experience-flow)
6. [Implementation Phases](#6-implementation-phases)
7. [File Structure](#7-file-structure)
8. [Testing Strategy](#8-testing-strategy)

---

## 1. Architecture Overview

### 1.1 Core Pattern: Human-in-the-Loop with `interrupt()`

LangGraph's `interrupt()` function pauses graph execution and returns control to the user. When the user responds, execution resumes via `Command(resume=<value>)`.

```python
from langgraph.types import interrupt, Command

def user_input_node(state):
    """Pause for user input."""
    user_response = interrupt({
        "prompt": state["next_prompt"],
        "context": state["current_phase"]
    })
    return {"user_input": user_response, "messages": [HumanMessage(content=user_response)]}
```

### 1.2 Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Conversational** | Agent speaks in first person, has personality ("Pete") |
| **Guided** | Clear progression through interview → draft → review |
| **Transparent** | Always shows mapped answers, missing fields, next steps |
| **Forgiving** | Handles intent changes, corrections, out-of-scope gracefully |
| **Checkpoint-able** | Full state persistence via LangGraph checkpointer |

### 1.3 High-Level Flow

```
┌─────────┐    ┌─────────────┐    ┌────────┐    ┌──────────────┐
│  Init   │───▶│  Interview  │───▶│ Draft  │───▶│   Review     │
│  Node   │    │  Subgraph   │    │Subgraph│    │  & Finalize  │
└─────────┘    └─────────────┘    └────────┘    └──────────────┘
                     │                  │              │
                     ▼                  ▼              ▼
               ┌──────────┐      ┌──────────┐   ┌──────────┐
               │  Intent  │      │ Generate │   │ Approve/ │
               │ Classify │      │ Element  │   │ Revise   │
               └──────────┘      └──────────┘   └──────────┘
```

---

## 2. State Model

### 2.1 AgentState (Main State)

```python
from typing import Annotated, Optional, Literal
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

# --- Interview Element with Metadata ---

class InterviewElement[T](BaseModel):
    """Interview element with value and lightweight metadata."""
    value: Optional[T] = None
    raw_input: Optional[str] = None  # Original text that yielded this value
    needs_confirmation: bool = False  # Flag for uncertain extractions
    confirmed: bool = False  # User explicitly confirmed
    
    @property
    def is_set(self) -> bool:
        """Check if value has been captured."""
        return self.value is not None
    
    def set_value(self, value: T, raw_input: Optional[str] = None, needs_confirmation: bool = False) -> None:
        """Set value with optional metadata."""
        self.value = value
        self.raw_input = raw_input
        self.needs_confirmation = needs_confirmation
        self.confirmed = False  # Reset on new value

    def confirm(self) -> None:
        """Mark this value as confirmed by user."""
        self.confirmed = True
        self.needs_confirmation = False

# --- Interview Data Model ---

class InterviewData(BaseModel):
    """Collected interview responses with per-element metadata."""
    position_title: InterviewElement[str] = Field(default_factory=InterviewElement)
    organization: InterviewElement[list[str]] = Field(default_factory=InterviewElement)  # Hierarchical
    series: InterviewElement[str] = Field(default_factory=InterviewElement)  # 4-digit OPM code
    grade: InterviewElement[str] = Field(default_factory=InterviewElement)  # GS-XX
    is_supervisory: InterviewElement[bool] = Field(default_factory=InterviewElement)
    num_supervised: InterviewElement[int] = Field(default_factory=InterviewElement)  # Conditional
    percent_supervising: InterviewElement[int] = Field(default_factory=InterviewElement)  # Conditional
    reports_to: InterviewElement[str] = Field(default_factory=InterviewElement)
    major_duties: InterviewElement[list[str]] = Field(default_factory=InterviewElement)
    qualifications: InterviewElement[list[str]] = Field(default_factory=InterviewElement)
    # ... additional fields
    
    def get_fields_needing_confirmation(self) -> list[str]:
        """Return fields that need user confirmation."""
        return [
            field_name for field_name, field_value in self
            if isinstance(field_value, InterviewElement) 
            and field_value.is_set 
            and field_value.needs_confirmation
        ]

# --- Draft Requirements ---

class DraftRequirement(BaseModel):
    """A requirement that must be present in a draft element."""
    id: str  # Unique identifier
    description: str  # Human-readable description
    element_name: str  # Which draft element this applies to
    rule_source: str  # Why this requirement exists (e.g., "supervisory_position", "gs_14_plus")
    check_type: Literal["must_include", "must_not_include", "must_reference", "format_rule", "content_rule"]
    keywords: Optional[list[str]] = None  # Keywords to check for (if applicable)
    regex_pattern: Optional[str] = None  # Regex pattern to match (if applicable)
    is_critical: bool = True  # If false, just a warning; if true, blocks approval

class DraftRequirements(BaseModel):
    """Collection of requirements for draft generation, derived from interview data."""
    requirements: list[DraftRequirement] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.now)
    interview_data_hash: Optional[str] = None  # To detect if interview changed
    
    def get_requirements_for_element(self, element_name: str) -> list[DraftRequirement]:
        """Get all requirements that apply to a specific draft element."""
        return [r for r in self.requirements if r.element_name == element_name]
    
    def get_critical_requirements(self) -> list[DraftRequirement]:
        """Get all critical requirements."""
        return [r for r in self.requirements if r.is_critical]

# --- Draft Element ---

class DraftElement(BaseModel):
    """A single element of the PD draft."""
    name: str
    content: str
    status: Literal["pending", "draft", "approved", "revision_requested"] = "pending"
    feedback: Optional[str] = None
    revision_count: int = 0
    
    # QA tracking against requirements
    requirements_checked: list[str] = Field(default_factory=list)  # Requirement IDs checked
    requirements_passed: list[str] = Field(default_factory=list)   # Requirement IDs passed
    requirements_failed: list[str] = Field(default_factory=list)   # Requirement IDs failed
    qa_notes: Optional[str] = None

class AgentState(TypedDict):
    """PD3r agent state."""
    # Message history
    messages: Annotated[list, add_messages]
    
    # Conversation phase
    phase: Literal["init", "interview", "requirements", "drafting", "review", "complete"]
    
    # Interview tracking
    interview_data: Optional[dict]  # Serialized InterviewData
    current_field: Optional[str]  # Which field we're asking about
    missing_fields: list[str]
    fields_needing_confirmation: list[str]  # Low-confidence or inferred fields to confirm
    
    # Intent classification
    last_intent: Optional[str]
    pending_question: Optional[str]  # Question to answer before continuing
    
    # Requirements (gathered from interview data)
    draft_requirements: Optional[dict]  # Serialized DraftRequirements
    
    # Drafting
    draft_elements: list[dict]  # List of serialized DraftElement
    current_element_index: int
    
    # Control
    should_end: bool
    next_prompt: str  # What to say next
```

### 2.2 Intent Classification Output

```python
class IntentClassification(BaseModel):
    """LLM output for intent classification."""
    
    primary_intent: Literal[
        "provide_information",
        "ask_question", 
        "confirm",
        "reject",
        "modify_answer",
        "request_restart",
        "quit",
        "unrecognized"
    ]
    
    # For provide_information
    field_mappings: Optional[list[FieldMapping]] = None
    
    # For ask_question
    question: Optional[str] = None
    is_hr_specific: Optional[bool] = None
    is_process_question: Optional[bool] = None
    
    # For modify_answer
    field_to_modify: Optional[str] = None
    new_value: Optional[str] = None
    
    confidence: float = Field(ge=0, le=1)

class FieldMapping(BaseModel):
    """Maps user input to a specific field."""
    field_name: str
    extracted_value: str
    parsed_value: Any  # Structured (e.g., list for organization)
    raw_input: str  # The exact text this was extracted from
    needs_confirmation: bool = False  # Flag if extraction is uncertain
```

---

## 3. Node Specifications

### 3.1 Init Node

**Purpose**: Initialize state, greet user, set up organizational context.

```python
def init_node(state: AgentState) -> dict:
    """Initialize the conversation."""
    greeting = (
        "Hi, I'm PD3r, but you can call me Pete. "
        "I help write Federal Position Descriptions. "
        "Would you like me to help you write a PD?"
    )
    return {
        "phase": "init",
        "interview_data": InterviewData().model_dump(),
        "missing_fields": list(REQUIRED_FIELDS),
        "draft_elements": [],
        "current_element_index": 0,
        "should_end": False,
        "next_prompt": greeting,
        "messages": [AIMessage(content=greeting)]
    }
```

### 3.2 User Input Node (Interrupt Point)

**Purpose**: Pause execution and collect user input.

```python
def user_input_node(state: AgentState) -> dict:
    """Collect user input via interrupt."""
    user_response = interrupt({
        "prompt": state["next_prompt"],
        "phase": state["phase"],
        "missing_fields": state.get("missing_fields", [])
    })
    return {
        "messages": [HumanMessage(content=user_response)]
    }
```

### 3.3 Intent Classification Node (LLM)

**Purpose**: Analyze user input and determine intent + extract information.

**Key Behaviors**:
- Use Jinja2 template that adapts based on `phase`
- Extract multiple intents if present (e.g., question + information)
- Map provided information to fields with confidence scores

```python
async def intent_classification_node(state: AgentState) -> dict:
    """Classify user intent using LLM with structured output."""
    
    # Build context-aware prompt
    prompt = render_template("intent_classification.jinja", {
        "phase": state["phase"],
        "current_field": state.get("current_field"),
        "interview_data": state.get("interview_data"),
        "user_message": state["messages"][-1].content
    })
    
    # Call LLM with structured output
    result = await llm.with_structured_output(IntentClassification).ainvoke(prompt)
    
    return {"last_intent": result.primary_intent, ...}
```

### 3.4 Router Node

**Purpose**: Conditional routing based on intent classification.

```python
def route_by_intent(state: AgentState) -> str:
    """Route to appropriate handler based on intent."""
    intent = state["last_intent"]
    
    # Hard-coded routes for system commands
    if intent == "quit":
        return "end_conversation"
    if intent == "request_restart":
        return "init"
    
    # Phase-specific routing
    if state["phase"] == "init":
        if intent in ("confirm", "provide_information"):
            return "start_interview"
        return "handle_init_response"
    
    if state["phase"] == "interview":
        if intent == "ask_question":
            return "answer_question"
        if intent == "provide_information":
            return "map_answers"
        if intent == "confirm":
            return "check_interview_complete"
        return "handle_interview_response"
    
    if state["phase"] == "drafting":
        if intent == "confirm":
            return "approve_element"
        if intent == "reject" or intent == "modify_answer":
            return "request_revision"
        return "handle_draft_response"
    
    return "handle_unrecognized"
```

### 3.5 Map Answers Node

**Purpose**: Apply extracted field values to interview data with metadata.

```python
def map_answers_node(state: AgentState) -> dict:
    """Apply mapped field values to interview data."""
    interview_data = InterviewData.model_validate(state["interview_data"])
    intent_result = state["intent_classification_result"]
    
    mapped_summary = []
    fields_needing_confirmation = []
    
    for mapping in intent_result.field_mappings:
        field: InterviewElement = getattr(interview_data, mapping.field_name)
        
        # Set value with metadata
        field.set_value(
            value=mapping.parsed_value,
            raw_input=mapping.raw_input,
            needs_confirmation=mapping.needs_confirmation
        )
        
        # Track uncertain extractions
        indicator = " ⚠️ (please confirm)" if mapping.needs_confirmation else ""
        if mapping.needs_confirmation:
            fields_needing_confirmation.append(mapping.field_name)
        
        mapped_summary.append(f"- {mapping.field_name}: {mapping.extracted_value}{indicator}")
    
    # Update missing fields
    missing = [f for f in REQUIRED_FIELDS if not getattr(interview_data, f).is_set]
    
    # Build response
    response = f"Great, I've mapped your answers:\n" + "\n".join(mapped_summary)
    
    if fields_needing_confirmation:
        response += f"\n\n⚠️ I'm not certain about: {', '.join(fields_needing_confirmation)}. Please confirm or correct."
    
    if missing:
        response += f"\n\nStill needed: {', '.join(missing)}"
        next_field = missing[0]
        response += f"\n\nNext, {FIELD_PROMPTS[next_field]}"
    
    return {
        "interview_data": interview_data.model_dump(),
        "missing_fields": missing,
        "fields_needing_confirmation": fields_needing_confirmation,
        "current_field": missing[0] if missing else None,
        "next_prompt": response,
        "messages": [AIMessage(content=response)]
    }
```

### 3.6 Answer Question Node (RAG/LLM)

**Purpose**: Handle user questions, potentially with RAG lookup.

```python
async def answer_question_node(state: AgentState) -> dict:
    """Answer user questions, with RAG for HR-specific queries."""
    question = state["pending_question"]
    
    # Check if HR-specific (would use RAG in full implementation)
    if state.get("is_hr_question"):
        # RAG lookup (placeholder)
        answer = await rag_lookup(question)
        response = f"{answer}\n\nNow, {state['next_prompt']}"
    else:
        # General question - LLM response
        response = await llm.ainvoke(f"Answer briefly: {question}")
        response = f"{response}\n\nBack to our PD: {state['next_prompt']}"
    
    return {
        "pending_question": None,
        "next_prompt": response,
        "messages": [AIMessage(content=response)]
    }
```

### 3.7 Gather Draft Requirements Node

**Purpose**: Analyze interview data and generate draft requirements based on complex business rules. This node runs after the interview is complete and before drafting begins.

```python
# Business rules that determine draft requirements
REQUIREMENT_RULES = {
    "supervisory": {
        "condition": lambda data: data.is_supervisory.value is True,
        "requirements": [
            DraftRequirement(
                id="sup_factor_required",
                description="Must include supervisory factor levels",
                element_name="factor_1_knowledge",
                rule_source="supervisory_position",
                check_type="must_include",
                keywords=["supervisory", "oversight", "staff direction"]
            ),
            DraftRequirement(
                id="sup_duties_required",
                description="Must describe supervisory responsibilities in major duties",
                element_name="major_duties",
                rule_source="supervisory_position",
                check_type="must_include",
                keywords=["supervise", "manage", "direct", "oversee"]
            ),
            # ... more supervisory requirements
        ]
    },
    "high_grade": {
        "condition": lambda data: data.grade.value and int(data.grade.value.split("-")[1]) >= 14,
        "requirements": [
            DraftRequirement(
                id="high_grade_complexity",
                description="GS-14+ positions must demonstrate high complexity",
                element_name="factor_4_complexity",
                rule_source="gs_14_plus",
                check_type="must_include",
                keywords=["unprecedented", "novel", "agency-wide", "national"]
            ),
            DraftRequirement(
                id="high_grade_scope",
                description="GS-14+ positions must show broad scope and effect",
                element_name="factor_5_scope_and_effect",
                rule_source="gs_14_plus",
                check_type="must_include",
                keywords=["agency", "department", "nationwide", "significant impact"]
            ),
        ]
    },
    "technical_series": {
        "condition": lambda data: data.series.value in ["2210", "1550", "1560"],
        "requirements": [
            DraftRequirement(
                id="tech_knowledge",
                description="Technical positions must specify technical competencies",
                element_name="factor_1_knowledge",
                rule_source="technical_series",
                check_type="must_include",
                keywords=["technical", "systems", "architecture", "engineering"]
            ),
        ]
    },
    # ... additional business rules
}

async def gather_draft_requirements_node(state: AgentState) -> dict:
    """
    Analyze interview data and generate requirements for draft elements.
    
    This node implements complex business rules that determine what MUST be
    present in each draft element based on the interview answers.
    """
    interview_data = InterviewData.model_validate(state["interview_data"])
    requirements = DraftRequirements()
    
    applied_rules = []
    
    # Apply each business rule
    for rule_name, rule_config in REQUIREMENT_RULES.items():
        try:
            if rule_config["condition"](interview_data):
                requirements.requirements.extend(rule_config["requirements"])
                applied_rules.append(rule_name)
        except Exception:
            # Log but don't fail if a rule can't be evaluated
            pass
    
    # Always-required base requirements
    requirements.requirements.extend([
        DraftRequirement(
            id="title_consistency",
            description="Position title must match interview data",
            element_name="introduction",
            rule_source="base_requirement",
            check_type="must_include",
            keywords=[interview_data.position_title.value] if interview_data.position_title.value else []
        ),
        DraftRequirement(
            id="series_reference",
            description="Series code must be referenced accurately",
            element_name="introduction",
            rule_source="base_requirement",
            check_type="must_reference",
            keywords=[interview_data.series.value] if interview_data.series.value else []
        ),
        DraftRequirement(
            id="duties_coverage",
            description="All major duties from interview must be addressed",
            element_name="major_duties",
            rule_source="base_requirement",
            check_type="content_rule",
            is_critical=True
        ),
    ])
    
    # Hash interview data to detect changes
    import hashlib
    data_str = interview_data.model_dump_json()
    requirements.interview_data_hash = hashlib.md5(data_str.encode()).hexdigest()
    
    # Build summary for user/logging
    response = f"I've analyzed your requirements and identified {len(requirements.requirements)} draft requirements based on:\n"
    response += "\n".join([f"- {rule}" for rule in applied_rules]) if applied_rules else "- Standard position requirements"
    response += "\n\nLet's start drafting!"
    
    return {
        "draft_requirements": requirements.model_dump(),
        "phase": "drafting",
        "next_prompt": response,
        "messages": [AIMessage(content=response)]
    }
```

### 3.8 Draft Generation Nodes

**Purpose**: Generate each element of the PD in sequence, informed by requirements.

```python
DRAFT_ELEMENTS = [
    "introduction",
    "background", 
    "major_duties",
    "factor_1",
    "factor_2",
    "factor_3",
    # ... etc
]

async def generate_element_node(state: AgentState) -> dict:
    """Generate next draft element, incorporating requirements."""
    element_name = DRAFT_ELEMENTS[state["current_element_index"]]
    interview_data = InterviewData.model_validate(state["interview_data"])
    requirements = DraftRequirements.model_validate(state["draft_requirements"])
    
    # Get requirements specific to this element
    element_requirements = requirements.get_requirements_for_element(element_name)
    
    # Render element-specific prompt with requirements
    prompt = render_template(f"draft_{element_name}.jinja", {
        "interview_data": interview_data,
        "previous_elements": state["draft_elements"],
        "requirements": element_requirements  # NEW: Pass requirements to prompt
    })
    
    content = await llm.ainvoke(prompt)
    
    element = DraftElement(
        name=element_name,
        content=content,
        status="draft"
    )
    
    response = f"Here's the {element_name}:\n\n{content}\n\nDo you approve or need revisions?"
    
    return {
        "draft_elements": state["draft_elements"] + [element.model_dump()],
        "next_prompt": response,
        "messages": [AIMessage(content=response)]
    }
```

### 3.9 QA Review Node (LLM)

**Purpose**: Self-review generated content against requirements before presenting to user.

```python
class QACheckResult(BaseModel):
    """Result of checking a single requirement."""
    requirement_id: str
    passed: bool
    explanation: str
    severity: Literal["critical", "warning", "info"]

class QAReview(BaseModel):
    """Full QA review result."""
    passes: bool
    check_results: list[QACheckResult]
    overall_feedback: str
    suggested_revisions: Optional[str] = None

async def qa_review_node(state: AgentState) -> dict:
    """LLM self-review of generated draft element against requirements."""
    current_element = DraftElement.model_validate(state["draft_elements"][-1])
    requirements = DraftRequirements.model_validate(state["draft_requirements"])
    
    # Get requirements for this element
    element_requirements = requirements.get_requirements_for_element(current_element.name)
    
    # Build review prompt with explicit requirements to check
    review_prompt = render_template("qa_review.jinja", {
        "element": current_element,
        "interview_data": state["interview_data"],
        "requirements": element_requirements  # NEW: Include requirements
    })
    
    review_result = await llm.with_structured_output(QAReview).ainvoke(review_prompt)
    
    # Update element with QA results
    current_element.requirements_checked = [r.id for r in element_requirements]
    current_element.requirements_passed = [
        cr.requirement_id for cr in review_result.check_results if cr.passed
    ]
    current_element.requirements_failed = [
        cr.requirement_id for cr in review_result.check_results if not cr.passed
    ]
    current_element.qa_notes = review_result.overall_feedback
    
    # Update the element in state
    updated_elements = state["draft_elements"][:-1] + [current_element.model_dump()]
    
    # Check if any CRITICAL requirements failed
    critical_failures = [
        cr for cr in review_result.check_results 
        if not cr.passed and cr.severity == "critical"
    ]
    
    if critical_failures:
        # Must rewrite - critical requirements not met
        return {
            "draft_elements": updated_elements,
            "needs_rewrite": True, 
            "qa_feedback": review_result.suggested_revisions or review_result.overall_feedback
        }
    
    return {
        "draft_elements": updated_elements,
        "needs_rewrite": False
    }
```

### 3.10 Synthesize Response Node

**Purpose**: Combine outputs from parallel nodes into coherent response.

```python
def synthesize_response_node(state: AgentState) -> dict:
    """Combine parallel node outputs into single AI message."""
    components = []
    
    if state.get("mapped_answers_response"):
        components.append(state["mapped_answers_response"])
    if state.get("question_answer_response"):
        components.append(state["question_answer_response"])
    
    combined = "\n\n".join(components)
    
    return {
        "next_prompt": combined,
        "messages": [AIMessage(content=combined)]
    }
```

### 3.11 Prepare Next Step Node

**Purpose**: Determine what to ask/do next based on state.

```python
def prepare_next_step_node(state: AgentState) -> dict:
    """Determine next action based on current state."""
    
    if state["phase"] == "interview":
        # Check for fields needing confirmation first
        if state.get("fields_needing_confirmation"):
            field = state["fields_needing_confirmation"][0]
            interview_data = InterviewData.model_validate(state["interview_data"])
            current_value = getattr(interview_data, field).value
            return {
                "current_field": field,
                "next_prompt": f"I captured {field} as '{current_value}' - is that correct?"
            }
        
        if not state["missing_fields"]:
            # Interview complete
            response = format_interview_summary(state["interview_data"])
            response += "\n\nDoes everything look ok?"
            return {
                "next_prompt": response,
                "phase": "requirements" if state.get("interview_confirmed") else "interview"
            }
        else:
            # Continue interview
            next_field = state["missing_fields"][0]
            return {
                "current_field": next_field,
                "next_prompt": FIELD_PROMPTS[next_field]
            }
    
    if state["phase"] == "requirements":
        # Transition to gather requirements
        return {"next_prompt": "Analyzing your requirements..."}
    
    if state["phase"] == "drafting":
        idx = state["current_element_index"]
        if idx >= len(DRAFT_ELEMENTS):
            return {"phase": "review", "next_prompt": "All elements complete! Final review..."}
        return {"next_prompt": f"Now generating: {DRAFT_ELEMENTS[idx]}"}
    
    return {}
```

---

## 4. Graph Structure

### 4.1 Main Graph

```python
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

def build_pd3r_graph():
    """Build the main PD3r agent graph."""
    
    builder = StateGraph(AgentState)
    
    # Core nodes
    builder.add_node("init", init_node)
    builder.add_node("user_input", user_input_node)
    builder.add_node("classify_intent", intent_classification_node)
    builder.add_node("route", route_by_intent)  # Actually handled by conditional edges
    
    # Interview nodes
    builder.add_node("map_answers", map_answers_node)
    builder.add_node("answer_question", answer_question_node)
    builder.add_node("check_interview_complete", check_interview_complete_node)
    
    # Requirements node (NEW - runs between interview and drafting)
    builder.add_node("gather_draft_requirements", gather_draft_requirements_node)
    
    # Drafting nodes
    builder.add_node("generate_element", generate_element_node)
    builder.add_node("qa_review", qa_review_node)
    builder.add_node("handle_revision", handle_revision_node)
    
    # Synthesis nodes
    builder.add_node("synthesize", synthesize_response_node)
    builder.add_node("prepare_next", prepare_next_step_node)
    
    # End nodes
    builder.add_node("end_conversation", end_conversation_node)
    
    # --- EDGES ---
    
    # Start
    builder.add_edge(START, "init")
    builder.add_edge("init", "user_input")
    
    # Main loop
    builder.add_edge("user_input", "classify_intent")
    builder.add_conditional_edges(
        "classify_intent",
        route_by_intent,
        {
            "map_answers": "map_answers",
            "answer_question": "answer_question",
            "check_interview_complete": "check_interview_complete",
            "gather_draft_requirements": "gather_draft_requirements",  # NEW
            "generate_element": "generate_element",
            "handle_revision": "handle_revision",
            "end_conversation": "end_conversation",
            "init": "init",
            "prepare_next": "prepare_next"
        }
    )
    
    # Post-processing → back to user input
    builder.add_edge("map_answers", "prepare_next")
    builder.add_edge("answer_question", "prepare_next")
    
    # Interview complete → gather requirements → drafting
    builder.add_conditional_edges(
        "check_interview_complete",
        lambda s: "gather_requirements" if s.get("interview_confirmed") else "continue",
        {"gather_requirements": "gather_draft_requirements", "continue": "prepare_next"}
    )
    builder.add_edge("gather_draft_requirements", "generate_element")  # NEW
    
    builder.add_edge("generate_element", "qa_review")
    builder.add_conditional_edges(
        "qa_review",
        lambda s: "rewrite" if s.get("needs_rewrite") else "present",
        {"rewrite": "generate_element", "present": "prepare_next"}
    )
    builder.add_edge("handle_revision", "generate_element")
    builder.add_edge("prepare_next", "user_input")
    
    # End
    builder.add_edge("end_conversation", END)
    
    # Compile with checkpointer
    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)
```

### 4.2 Simplified Graph Diagram

```
                    ┌─────────────────────────────────────────────────────────────────┐
                    │                         MAIN LOOP                                │
                    │                                                                  │
  START ──▶ init ──▶│  user_input ──▶ classify_intent ──▶ router                      │
                    │       ▲                              │                           │
                    │       │         ┌────────────────────┼───────────────────┐       │
                    │       │         ▼                    ▼                   ▼       │
                    │       │    map_answers    answer_question     check_interview    │
                    │       │         │              │                    │            │
                    │       │         │              │            [confirmed?]         │
                    │       │         │              │              │         │        │
                    │       │         │              │              ▼         │        │
                    │       │         │              │    gather_draft_requirements    │
                    │       │         │              │              │                  │
                    │       │         │              │              ▼                  │
                    │       │         │              │       generate_element          │
                    │       │         │              │              │                  │
                    │       │         │              │              ▼                  │
                    │       │         │              │         qa_review               │
                    │       │         │              │         [pass?]                 │
                    │       │         │              │         │     │                 │
                    │       │         │              │    [rewrite]  │                 │
                    │       │         ▼              ▼         │     ▼                 │
                    │       │    ┌─────────────────────────────────────┐               │
                    │       └────│          prepare_next               │◀──────────────┘
                    │            └─────────────────────────────────────┘               │
                    └─────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
                                   end_conversation ──▶ END
```

### 4.3 Phase Transitions

```
┌──────────┐    ┌───────────────┐    ┌──────────────────────┐    ┌──────────┐    ┌──────────┐
│   init   │───▶│   interview   │───▶│     requirements     │───▶│ drafting │───▶│  review  │
│          │    │               │    │                      │    │          │    │          │
│ Greeting │    │ Collect data  │    │ gather_draft_reqs    │    │ Generate │    │ Final    │
│          │    │ with metadata │    │ (business rules)     │    │ + QA     │    │ approval │
└──────────┘    └───────────────┘    └──────────────────────┘    └──────────┘    └──────────┘
                       │                       │
                       │                       │
                       ▼                       ▼
              ┌────────────────┐      ┌────────────────────┐
              │ Track metadata │      │ Check requirements │
              │ - confidence   │      │ in qa_review_node  │
              │ - source       │      │ - critical pass?   │
              │ - timestamp    │      │ - rewrite if fail  │
              └────────────────┘      └────────────────────┘
```

---

## 5. User Experience Flow

### 5.1 Conversation Phases

| Phase | Description | Exit Condition |
|-------|-------------|----------------|
| **init** | Greeting, confirm user wants help | User confirms |
| **interview** | Collect PD requirements field-by-field with metadata tracking | All required fields populated + low-confidence fields confirmed + user confirms |
| **requirements** | Analyze interview data, generate draft requirements from business rules | Requirements generated |
| **drafting** | Generate each PD element sequentially, QA checks against requirements | All elements approved |
| **review** | Final approval of complete PD | User approves |
| **complete** | Export/save, offer to write another | User ends or restarts |

### 5.2 Sample Conversation (Happy Path)

```
Pete: Hi, I'm PD3r, but you can call me Pete. I help write Federal Position 
      Descriptions. Would you like me to help you write a PD?

User: Sure, that sounds good.

Pete: Great! To write a PD I need the following information:
      - Position Title
      - Organization (hierarchical)
      - Series Code (4-digit OPM)
      - Grade Level
      - Is the position supervisory?
      ...
      
      Let's start: What is the position title?

User: I'm hiring an IT Integrations Specialist who will work under the Chief AI Officer

Pete: Great, I've mapped your answers:
      - Position Title: IT Integrations Specialist
      - Reports To: Chief AI Officer
      
      Still needed: Series, Grade, Organization, Is Supervisory
      
      Next, is this position supervisory?

User: Why does that matter?

Pete: Supervisory positions require additional evaluation factors under OPM 
      guidelines. You can learn more here: [link]
      
      Back to our PD: Is this position supervisory?

User: No, it's not supervisory.

Pete: Got it:
      - Is Supervisory: No
      
      Still needed: Series, Grade, Organization
      
      What's the 4-digit OPM series code?

... [interview continues] ...

Pete: That wraps up the interview! Here are your answers:
      
      Position Title: IT Integrations Specialist
      Series: 2210
      Grade: GS-13
      Organization: VHA > Digital Health Office > OCTO
      Reports To: Chief AI Officer
      Is Supervisory: No
      ...
      
      Does everything look ok?

User: Actually, can we change the grade to GS-14?

Pete: Sure, I've updated:
      - Grade: GS-14
      
      Here are your updated answers:
      [summary]
      
      Does everything look ok now?

User: Yes.

Pete: Great! We're ready to start writing. A position description consists of:
      - Introduction
      - Background  
      - Major Duties
      - Factor Levels (1-9)
      - Supervisory Factors (if applicable)
      
      Let's start with the Introduction:
      
      ---
      [Generated Introduction]
      ---
      
      Do you approve or need revisions?

User: That's good.

Pete: ✓ Introduction approved.
      
      Next, here's the Background section:
      
      ---
      [Generated Background]
      ---
      
      Do you approve or need revisions?

User: Can you emphasize the AI/ML aspects more?

Pete: Sure, working on that revision...
      
      ---
      [Revised Background with AI/ML emphasis]
      ---
      
      How's this?

... [drafting continues] ...

Pete: Congratulations! We've completed your position description. Here's the 
      final document for your review:
      
      [Complete PD]
      
      Would you like to export this or make any changes?

User: Export to Word please.

Pete: ✓ Exported to output/IT_Integrations_Specialist_PD.docx
      
      Would you like to write another PD?

User: I hope I don't have to do another for a while.

Pete: Ha! Thanks for working with me. Have a nice day!
```

### 5.3 Handling Edge Cases

| Scenario | Handling |
|----------|----------|
| User provides multiple answers at once | Intent classifier extracts all, flags uncertain ones for confirmation |
| User asks off-topic question | Polite redirect, answer if possible, return to flow |
| User wants to go back | Allow field modification at any point |
| User abandons mid-conversation | State persisted, can resume later |
| Invalid input (e.g., bad series code) | Validate, explain format, ask again |
| User says something mean to Pete | Light deflection with humor, continue professionally |
| Uncertain extraction | Flag `needs_confirmation=True`, ask user to verify |
| QA requirement failure | Automatic rewrite for critical failures, present warning for non-critical |

---

## 6. Implementation Phases

### Phase 1: Foundation (Week 1)
**Goal**: Basic conversation loop with interrupt/resume

- [ ] Update `AgentState` in `src/models/state.py` with new fields
- [ ] Create `InterviewElement[T]` generic model (value + raw_input + needs_confirmation + confirmed)
- [ ] Create `InterviewData` model using `InterviewElement` fields
- [ ] Implement `init_node` 
- [ ] Implement `user_input_node` with `interrupt()`
- [ ] Basic intent classification (confirm/reject only)
- [ ] Simple routing
- [ ] Wire up main graph with checkpointer
- [ ] Test: Can greet, ask confirmation, handle yes/no
- [ ] Test: InterviewElement value/confirmation tracking works

### Phase 2: Interview Flow (Week 2)
**Goal**: Complete interview collection with confirmation handling

- [ ] Full `IntentClassification` schema
- [ ] `FieldMapping` model with `needs_confirmation` flag
- [ ] LLM-powered intent classification node
- [ ] `map_answers_node` implementation
- [ ] Confirmation flow for uncertain extractions
- [ ] `answer_question_node` (basic, no RAG)
- [ ] Field validation (series format, grade format, etc.)
- [ ] Interview summary and confirmation
- [ ] Test: Can collect all required fields through conversation
- [ ] Test: Uncertain fields trigger confirmation prompts

### Phase 3: Requirements & Draft Generation (Week 3)
**Goal**: Business rules engine and requirement-driven drafting

- [ ] `DraftRequirement` model with check types
- [ ] `DraftRequirements` collection model
- [ ] `REQUIREMENT_RULES` business rules configuration
- [ ] `gather_draft_requirements_node` implementation
- [ ] `DraftElement` model with requirement tracking fields
- [ ] `QACheckResult` and `QAReview` models
- [ ] Prompt templates for each element with requirements context (`draft_introduction.jinja`, etc.)
- [ ] `generate_element_node` with requirements awareness
- [ ] `qa_review_node` checking against requirements
- [ ] `handle_revision_node`
- [ ] Automatic rewrite loop for critical requirement failures
- [ ] Test: Requirements generated correctly from interview data
- [ ] Test: QA catches missing requirements
- [ ] Test: Rewrite loop produces compliant content

### Phase 4: Polish & Export (Week 4)
**Goal**: Complete UX and output

- [ ] Final document assembly
- [ ] Export to markdown/Word
- [ ] "Write another?" flow
- [ ] RAG integration for HR questions (stub/basic)
- [ ] Error handling and graceful recovery
- [ ] Personality tuning (Pete's voice)
- [ ] End-to-end integration test with full metadata trail
- [ ] Test: Complete flow from interview to export with all metadata preserved

---

## 7. File Structure

```
src/
├── main.py                          # CLI entry point
├── graphs/
│   ├── __init__.py
│   ├── main_graph.py                # Main PD3r graph builder
│   ├── export.py                    # Graph visualization
│   └── subgraphs/
│       ├── interview_graph.py       # (Optional) Interview subgraph
│       └── drafting_graph.py        # (Optional) Drafting subgraph
├── models/
│   ├── __init__.py
│   ├── state.py                     # AgentState TypedDict
│   ├── interview.py                 # InterviewData, InterviewElement
│   ├── position.py                  # PositionDescription (final output)
│   ├── intent.py                    # IntentClassification, FieldMapping
│   ├── draft.py                     # DraftElement, QAReview, QACheckResult
│   └── requirements.py              # DraftRequirement, DraftRequirements
├── nodes/
│   ├── __init__.py
│   ├── init_node.py
│   ├── user_input_node.py
│   ├── intent_classification_node.py
│   ├── map_answers_node.py
│   ├── answer_question_node.py
│   ├── gather_draft_requirements_node.py  # Business rules engine
│   ├── generate_element_node.py
│   ├── qa_review_node.py
│   ├── prepare_next_node.py
│   └── routing.py                   # Routing functions
├── prompts/
│   ├── __init__.py
│   ├── loader.py                    # Jinja2 loader utility
│   └── templates/
│       ├── intent_classification.jinja
│       ├── field_extraction.jinja
│       ├── draft_introduction.jinja
│       ├── draft_background.jinja
│       ├── draft_major_duties.jinja
│       ├── draft_factor_N.jinja     # Template for factors
│       ├── qa_review.jinja          # Includes requirements checking
│       └── answer_question.jinja
├── tools/
│   ├── __init__.py
│   ├── export_tools.py              # Word/markdown export
│   └── rag_tools.py                 # RAG lookup (stub)
├── rules/
│   ├── __init__.py
│   └── requirement_rules.py         # REQUIREMENT_RULES configuration
└── constants.py                     # REQUIRED_FIELDS, FIELD_PROMPTS, DRAFT_ELEMENTS
```

---

## 8. Testing Strategy

### 8.1 Unit Tests

| Test | File | Description |
|------|------|-------------|
| State model validation | `test_unit_models.py` | InterviewData, InterviewElement |
| Interview element | `test_unit_interview.py` | Value setting, confirmation flow |
| Intent classification parsing | `test_unit_intent.py` | Mock LLM outputs |
| Field validation | `test_unit_validation.py` | Series, grade, org formats |
| Routing logic | `test_unit_routing.py` | All intent→node mappings |
| Requirements generation | `test_unit_requirements.py` | Business rules → requirements |
| QA check results | `test_unit_qa.py` | Requirement checking logic |

### 8.2 Node Tests

| Test | File | Description |
|------|------|-------------|
| Init node | `test_node_init.py` | Correct greeting, state setup |
| Map answers | `test_node_map_answers.py` | Field extraction → state update |
| Gather requirements | `test_node_requirements.py` | Interview data → draft requirements |
| Generate element | `test_node_generate.py` | Prompt rendering with requirements context |
| QA review | `test_node_qa.py` | Requirements checking, rewrite triggering |

### 8.3 Integration Tests

| Test | File | Description |
|------|------|-------------|
| Happy path interview | `test_integration_interview.py` | Full interview flow |
| Confirmation flow | `test_integration_confirmation.py` | Prompts for uncertain values |
| Requirements flow | `test_integration_requirements.py` | Interview → requirements → draft |
| Happy path draft | `test_integration_draft.py` | Full drafting flow with QA |
| QA failure recovery | `test_integration_qa.py` | Rewrite loop on requirement failures |
| Edge cases | `test_integration_edges.py` | Modification, questions, errors |

### 8.4 Test Fixtures

```python
# tests/conftest.py

@pytest.fixture
def mock_llm():
    """Mock LLM that returns predictable responses."""
    ...

@pytest.fixture
def sample_interview_element():
    """Sample InterviewElement with metadata."""
    from src.models.interview import InterviewElement, InterviewElementMeta
    from src.models.enums import ConfidenceLevel, SourceType
    
    element = InterviewElement[str]()
    element.set_value(
        value="IT Specialist",
        raw_input="The position is for an IT Specialist"
    )
    return element

@pytest.fixture
def sample_interview_data():
    """Complete InterviewData for drafting tests."""
    from src.models.interview import InterviewData
    
    data = InterviewData()
    data.position_title.set_value("IT Specialist", raw_input="IT Specialist position")
    data.series.set_value("2210", raw_input="series 2210")
    data.grade.set_value("GS-13", raw_input="GS-13")
    data.organization.set_value(["VHA", "Digital Health Office"], raw_input="VHA, Digital Health Office")
    data.is_supervisory.set_value(False, raw_input="not supervisory")
    data.reports_to.set_value("Director", raw_input="reports to Director")
    data.major_duties.set_value(
        ["Develop software", "Manage systems", "Coordinate projects"],
        raw_input="develop software, manage systems, coordinate projects"
    )
    data.qualifications.set_value(
        ["BS in Computer Science", "5 years experience"],
        raw_input="BS in CS, 5 years experience"
    )
    return data

@pytest.fixture
def sample_draft_requirements():
    """Sample DraftRequirements for QA tests."""
    from src.models.requirements import DraftRequirement, DraftRequirements
    
    return DraftRequirements(
        requirements=[
            DraftRequirement(
                id="title_consistency",
                description="Position title must match interview data",
                element_name="introduction",
                rule_source="base_requirement",
                check_type="must_include",
                keywords=["IT Specialist"]
            ),
            DraftRequirement(
                id="series_reference",
                description="Series code must be referenced",
                element_name="introduction",
                rule_source="base_requirement",
                check_type="must_reference",
                keywords=["2210"]
            ),
        ]
    )

@pytest.fixture
def compiled_graph(mock_llm):
    """Compiled graph with mock LLM."""
    ...
```

---

## Appendix A: Required Fields

```python
REQUIRED_FIELDS = [
    "position_title",
    "series",
    "grade", 
    "organization",
    "reports_to",
    "is_supervisory",
    "major_duties",  # At least 3
    "qualifications",  # At least 2
]

CONDITIONAL_FIELDS = {
    "is_supervisory": {
        True: ["num_supervised", "percent_supervising"]
    }
}

FIELD_PROMPTS = {
    "position_title": "What is the position title as it appears on the org chart?",
    "series": "What is the 4-digit OPM series code (e.g., 2210 for IT)?",
    "grade": "What is the GS grade level (e.g., GS-13)?",
    "organization": "Where does this position fall in the organization? Include higher offices.",
    "reports_to": "Who does this position report to?",
    "is_supervisory": "Is this position supervisory?",
    "num_supervised": "How many people will this position supervise?",
    "percent_supervising": "What percent of time will be spent on supervisory duties?",
    "major_duties": "What are the major duties of this position? (list at least 3)",
    "qualifications": "What qualifications are required? (list at least 2)",
}
```

## Appendix B: Draft Elements

```python
DRAFT_ELEMENTS = [
    "introduction",
    "background",
    "major_duties",
    "factor_1_knowledge",
    "factor_2_supervisory_controls",
    "factor_3_guidelines",
    "factor_4_complexity",
    "factor_5_scope_and_effect",
    "factor_6_personal_contacts",
    "factor_7_purpose_of_contacts",
    "factor_8_physical_demands",
    "factor_9_work_environment",
]

# Supervisory positions add:
SUPERVISORY_ELEMENTS = [
    "supervisory_factor_1",
    "supervisory_factor_2",
    # ...
]
```

---

## Appendix C: UX & Personality Guidelines

### Pete's Voice

Pete is **friendly, professional, and slightly playful**. He:
- Uses contractions ("I'm", "you're", "that's")
- Acknowledges user input positively ("Great!", "Got it", "Sure thing")
- Uses first person and addresses user directly
- Offers brief explanations when redirecting
- Has light humor at natural moments (especially at conversation end)

### Response Patterns

**Acknowledgment Phrases** (rotate for variety):
```
"Great, I've mapped your answers:"
"Got it! Here's what I captured:"
"Perfect, I've recorded:"
"Thanks! I've noted:"
```

**Transition Phrases** (between topics):
```
"Next, I need to know..."
"Moving on: ..."
"Up next: ..."
"Now let's talk about..."
```

**Working Phrases** (during generation):
```
"Just a moment..."
"Working on that..."
"Let me put that together..."
"One sec while I draft that..."
"Sure thing, give me a moment..."
```

**Completion Phrases**:
```
"Here you go:"
"Here's what I came up with:"
"Take a look:"
"How's this?"
```

### Interview UX Details

1. **Show the full list upfront** - After user confirms they want help, show ALL fields needed with brief descriptions
2. **Always show progress** - "Mapped Answers" + "Still Needed" after each input
3. **Smart field ordering** - Ask conditional fields immediately after their trigger (is_supervisory → num_supervised)
4. **Allow multi-field input** - User can provide multiple answers at once; acknowledge all
5. **Questions don't derail** - Answer question, then return to the pending field with "Back to our PD:"

### Draft UX Details

1. **Explain the structure first** - Before generating, explain what elements will be created
2. **One element at a time** - Don't overwhelm; generate, present, get approval, then move on
3. **Clear revision flow** - "Thanks, I'll work that into the draft." → Generate → "Here's an updated draft incorporating your feedback:"
4. **Allow late revisions** - User can request changes to ANY element at any time during review phase
5. **Celebrate completion** - "Great job, we've completed your position description!"

### Error Recovery UX

| Situation | Pete's Response |
|-----------|-----------------|
| Invalid series code | "Hmm, that doesn't look like a valid series code. OPM series are 4 digits (like 2210 for IT). What's the correct code?" |
| Unclear input | "I'm not quite sure I understood that. Could you rephrase?" |
| Off-topic question | "Good question! [brief answer]. Now, back to our PD: [current field prompt]" |
| User frustration | "No worries, let's take this one step at a time. [simplified prompt]" |
| System error | "Oops, something went wrong on my end. Let me try that again." |

### Conversation End Patterns

**User wants to write another**:
```
Pete: Would you like to write another PD?
User: Yes please.
Pete: Great! Let's start fresh. What's the position title for this one?
```

**User is done**:
```
Pete: Would you like to write another PD?
User: No, I'm good for now.
Pete: Thanks for working with me! Feel free to come back anytime. Have a great day!
```

**User makes a joke/light comment**:
```
User: I hope I don't have to do another for a while.
Pete: Ha! I hear you. Thanks for working with me—have a nice day!
```

---

## Appendix D: Field Configuration Template

Each interview field should have a configuration like:

```python
FIELD_CONFIG = {
    "position_title": {
        "prompt": "What is the position title as it appears on the org chart?",
        "type": "str",
        "required": True,
        "validation": lambda x: len(x.strip()) >= 3,
        "validation_error": "Position title must be at least 3 characters.",
        "extraction_hint": "Look for job title, role name, or position name.",
        "examples": ["IT Specialist", "Program Analyst", "Supervisory Nurse"]
    },
    "series": {
        "prompt": "What is the 4-digit OPM series code (e.g., 2210 for IT)?",
        "type": "str",
        "required": True,
        "validation": lambda x: re.match(r"^\d{4}$", x.strip()),
        "validation_error": "Series must be exactly 4 digits.",
        "extraction_hint": "Look for 4-digit number, often preceded by 'series' or OPM reference.",
        "examples": ["2210", "0343", "0610"]
    },
    "organization": {
        "prompt": "Where does this position fall in the organization? Include higher offices.",
        "type": "list[str]",
        "required": True,
        "validation": lambda x: len(x) >= 1,
        "validation_error": "Please provide at least one organizational level.",
        "extraction_hint": "Parse hierarchical structure, highest level first.",
        "examples": [["VHA", "Digital Health Office", "OCTO"], ["VA", "OIT"]]
    },
    "is_supervisory": {
        "prompt": "Is this position supervisory?",
        "type": "bool",
        "required": True,
        "triggers": {
            True: ["num_supervised", "percent_supervising"]
        },
        "extraction_hint": "Look for yes/no, supervisor, manages, leads team, etc."
    },
    # ... etc
}
```

This configuration drives:
- Prompt generation
- Intent classification hints
- Field validation
- Conditional field triggering
- Progress tracking

---

## Appendix E: Requirement Rules Configuration

Business rules that generate draft requirements based on interview data:

```python
from src.models.requirements import DraftRequirement

REQUIREMENT_RULES = {
    # --- Position Type Rules ---
    "supervisory": {
        "condition": lambda data: data.is_supervisory.value is True,
        "requirements": [
            DraftRequirement(
                id="sup_factor_required",
                description="Must include supervisory factor levels",
                element_name="factor_1_knowledge",
                rule_source="supervisory_position",
                check_type="must_include",
                keywords=["supervisory", "oversight", "staff direction"],
                is_critical=True
            ),
            DraftRequirement(
                id="sup_duties_required",
                description="Must describe supervisory responsibilities in major duties",
                element_name="major_duties",
                rule_source="supervisory_position",
                check_type="must_include",
                keywords=["supervise", "manage", "direct", "oversee"],
                is_critical=True
            ),
        ]
    },
    
    # --- Grade Level Rules ---
    "high_grade_14_plus": {
        "condition": lambda data: (
            data.grade.value and 
            int(data.grade.value.split("-")[1]) >= 14
        ),
        "requirements": [
            DraftRequirement(
                id="high_grade_complexity",
                description="GS-14+ must demonstrate unprecedented/novel work",
                element_name="factor_4_complexity",
                rule_source="gs_14_plus",
                check_type="must_include",
                keywords=["unprecedented", "novel", "agency-wide", "national"],
                is_critical=True
            ),
            DraftRequirement(
                id="high_grade_scope",
                description="GS-14+ must show broad organizational impact",
                element_name="factor_5_scope_and_effect",
                rule_source="gs_14_plus",
                check_type="must_include",
                keywords=["agency", "department", "nationwide", "significant"],
                is_critical=True
            ),
        ]
    },
    
    "entry_level_7_below": {
        "condition": lambda data: (
            data.grade.value and 
            int(data.grade.value.split("-")[1]) <= 7
        ),
        "requirements": [
            DraftRequirement(
                id="entry_supervision",
                description="Entry-level must reference close supervision",
                element_name="factor_2_supervisory_controls",
                rule_source="gs_7_below",
                check_type="must_include",
                keywords=["close supervision", "detailed instructions", "guidance"],
                is_critical=True
            ),
        ]
    },
    
    # --- Series-Specific Rules ---
    "it_series_2210": {
        "condition": lambda data: data.series.value == "2210",
        "requirements": [
            DraftRequirement(
                id="it_technical_knowledge",
                description="IT positions must specify technical competencies",
                element_name="factor_1_knowledge",
                rule_source="series_2210",
                check_type="must_include",
                keywords=["information technology", "systems", "software", "hardware"],
                is_critical=True
            ),
        ]
    },
}

# Base requirements applied to ALL positions
BASE_REQUIREMENTS = [
    DraftRequirement(
        id="title_consistency",
        description="Position title must match throughout",
        element_name="introduction",
        rule_source="base",
        check_type="must_include",
        is_critical=True
    ),
    DraftRequirement(
        id="series_accuracy",
        description="Series code must be referenced accurately",
        element_name="introduction",
        rule_source="base",
        check_type="must_reference",
        is_critical=True
    ),
    DraftRequirement(
        id="grade_alignment",
        description="Content must align with grade level expectations",
        element_name="factor_4_complexity",
        rule_source="base",
        check_type="content_rule",
        is_critical=True
    ),
]
```

---

## Appendix F: Interview Element Reference

Each interview field uses `InterviewElement[T]` which wraps the value with lightweight metadata:

| Field | Type | Purpose |
|-------|------|---------|
| `value` | `T` | The actual captured value (str, bool, list, etc.) |
| `raw_input` | `Optional[str]` | The exact user text this was extracted from |
| `needs_confirmation` | `bool` | Flag when extraction is uncertain |
| `confirmed` | `bool` | Whether user explicitly confirmed the value |

### Confirmation Flow

| Scenario | `needs_confirmation` | `confirmed` | User Experience |
|----------|---------------------|-------------|-----------------|
| Direct, clear answer | `False` | `False` | Value accepted immediately |
| Ambiguous extraction | `True` | `False` | "I captured X as Y - is that correct?" |
| User confirms | `False` | `True` | Proceed with confidence |
| User corrects | `False` | `False` | New value stored, flow continues |

---

