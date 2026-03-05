# Prompts Reference

> **Last Updated**: 2026-01-16  
> **Module Path**: `src/prompts/`

---

## Overview

All LLM prompts are Jinja2 templates stored in `src/prompts/templates/`. Nodes import and render prompts — **never define inline**.

---

## Template Files

```
src/prompts/
├── __init__.py              # get_template() helper
└── templates/
    ├── intent_classification.jinja  # Intent + field extraction
    ├── answer_question.jinja        # Answer user HR/PD questions
    ├── draft.jinja                  # Generic PD section generation
    ├── draft_introduction.jinja     # Introduction section
    ├── draft_major_duties.jinja     # Major duties section
    └── qa_review.jinja              # QA review against requirements
```

---

## Usage Pattern

```python
from src.prompts import get_template

template = get_template("intent_classification.jinja")
prompt = template.render(
    user_message=state["messages"][-1].content,
    phase=state["phase"],
    field_definitions=FIELD_DEFINITIONS,
    current_field=state.get("current_field"),
)
```

---

## Configuration-Driven Templates

Templates use field definitions from `src/constants.py` (derived from `src/config/intake_fields.py`):

```python
from src.constants import FIELD_DEFINITIONS, FIELD_PROMPTS

template = get_template("intent_classification.jinja")
prompt = template.render(
    field_definitions=FIELD_DEFINITIONS,
    user_message=user_message,
    phase=state["phase"],
)
```

This allows field definitions, extraction hints, and validation rules to be controlled via configuration rather than hardcoded in templates.

---

## Template Descriptions

### `intent_classification.jinja`
Classifies user intent and extracts field values. Returns structured `IntentClassification` output.

**Variables**:
- `user_message` - The user's input text
- `phase` - Current conversation phase
- `field_definitions` - Dict of all interview fields with metadata
- `current_field` - Field currently being asked about (if any)
- `interview_data` - Current collected data (for context)

### `answer_question.jinja`
Generates helpful answers to user questions using the non-RAG path. Used for process questions and general clarifications. Contains detailed explanation of the PD3r 5-phase process for context.

**Variables**:
- `question` - The user's question
- `phase` - Current conversation phase
- `current_field` - Field currently being collected (if any)
- `interview_summary` - Summary of collected interview data

### `draft_introduction.jinja`
Generates the Introduction section of the PD.

**Variables**:
- `interview_data` - Collected interview data
- `fes_evaluation` - FES evaluation results
- `requirements` - Requirements to meet

### `draft_major_duties.jinja`
Generates the Major Duties section with proper duty sections and weights.

**Variables**:
- `interview_data` - Collected interview data
- `duty_template` - Series-specific duty template (if applicable)
- `requirements` - Requirements to meet

### `qa_review.jinja`
Reviews draft content against requirements and generates QA feedback.

**Variables**:
- `element_name` - Which element is being reviewed
- `content` - Draft content to review
- `requirements` - List of requirements to check

---

## Best Practices

1. **No inline prompts** — All prompts must be in template files
2. **Use structured output** — Configure LLM for Pydantic model output
3. **Pass config, not hardcoded text** — Use `FIELD_DEFINITIONS` etc.
4. **Include context** — Pass relevant state for better LLM responses
5. **Version control templates** — Track prompt changes in git

---

## Creating a New Template

1. Create `.jinja` file in `src/prompts/templates/`
2. Define clear variable interface in file header comments
3. Use Jinja2 syntax for conditionals, loops, filters
4. Document in this file
5. Test with sample inputs
