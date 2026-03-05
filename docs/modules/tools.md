# Tools Reference

> **Last Updated**: 2026-01-16  
> **Module Path**: `src/tools/`  
> **Status**: Active — Phase 3 complete

---

## Overview

Tools are functions the agent can invoke during execution. The module implements LLM-driven tool selection per [ADR-006](../decisions/006-llm-driven-routing.md).

Tool categories:
- **Interview tools** — Field collection during interview phase
- **Knowledge tools** — RAG search and FES/grade guidance
- **Drafting tools** — Section writing and revision (NEW Phase 3)
- **QA tools** — Quality review and approval (NEW Phase 3)
- **Export tools** — Document generation (Markdown, Word)
- **PDF/Vector tools** — Document ingestion and search

---

## Tool Summary

| Category | Module | Tools | Purpose |
|----------|--------|-------|---------|
| Interview | `interview_tools.py` | 6 | Field collection, user questions |
| Knowledge | `knowledge_tools.py` | 3 | RAG search, FES/grade lookup |
| Drafting | `drafting_tools.py` | 5 | Write/revise sections |
| QA | `qa_tools.py` | 5 | Review, approve sections |
| Export | `export_tools.py` | 5 | Markdown/Word export |
| RAG | `rag_tools.py` | 3 | Vector search, answer |
| PDF | `pdf_loader.py` | 3 | Load, chunk PDFs |
| Vector | `vector_store.py` | 4 | ChromaDB operations |

---

## Interview Tools (`src/tools/interview_tools.py`)

LLM-driven field collection. See [ADR-006](../decisions/006-llm-driven-routing.md).

| Tool | Purpose |
|------|---------|
| `save_field_answer` | Save user's answer to an interview field |
| `confirm_field_value` | Confirm a value that needs verification |
| `answer_user_question` | Answer user questions about the process |
| `check_interview_complete` | Check if all required fields collected |
| `request_field_clarification` | Ask user for clarification |
| `modify_field_value` | Update a previously collected field |

**Helper Functions:**
- `get_next_required_field(interview_data)` — Get next field to collect
- `get_field_context(field_name)` — Get metadata for a field
- `get_interview_progress(interview_data)` — Get collection progress

---

## Knowledge Tools (`src/tools/knowledge_tools.py`)

RAG and FES/grade lookup tools for answering questions.

| Tool | Purpose |
|------|---------|
| `search_knowledge_base` | Search OPM/HR documents via RAG |
| `get_fes_factor_guidance` | Get FES factor level for grade |
| `get_grade_requirements` | Get point requirements for grade |

---

## Drafting Tools (`src/tools/drafting_tools.py`) — NEW Phase 3

Tools for writing and revising PD sections.

| Tool | Purpose |
|------|---------|
| `write_section` | Generate a PD section from interview data |
| `revise_section` | Revise a section based on QA feedback |
| `get_section_status` | Get status of all draft elements |
| `list_available_sections` | List all available PD sections |
| `get_section_requirements` | Get requirements for a section |

**Usage:**
```python
from src.tools.drafting_tools import write_section, revise_section

# Write a section
content = write_section.invoke({
    "section_name": "introduction",
    "interview_data_dict": interview_data.model_dump(),
    "fes_evaluation_dict": fes_eval.model_dump(),  # Optional
})

# Revise after QA failure
revised = revise_section.invoke({
    "section_name": "introduction",
    "current_content": content,
    "qa_feedback": "Missing complexity indicators",
    "qa_failures": ["REQ-001"],
    "interview_data_dict": interview_data.model_dump(),
})
```

---

## QA Tools (`src/tools/qa_tools.py`) — NEW Phase 3

Tools for quality assurance review and approval workflow.

| Tool | Purpose |
|------|---------|
| `qa_review_section` | Review section against requirements |
| `check_qa_status` | Get QA status across all sections |
| `request_qa_rewrite` | Request rewrite for failed section |
| `request_section_approval` | Request human approval |
| `get_qa_thresholds` | Get QA threshold settings |

**Thresholds:**
- Pass threshold: 80% confidence
- Rewrite threshold: 50% confidence
- Max rewrites: 1 per section

**Usage:**
```python
from src.tools.qa_tools import qa_review_section, request_section_approval

# Review a section
result = qa_review_section.invoke({
    "section_name": "introduction",
    "draft_content": "The position is located in...",
    "requirements_dict": requirements.model_dump(),
})
# Returns: "✅ PASSED" or "❌ FAILED" with feedback

# Request approval after QA passes
approval = request_section_approval.invoke({
    "section_name": "introduction",
    "section_content": "The position is located in...",
    "qa_passed": True,
    "qa_confidence": 0.85,
})
```

---

## Export Tools (`src/tools/export_tools.py`)

| Tool | Purpose |
|------|---------|
| `export_to_markdown` | Export PD to .md file |
| `export_to_word` | Export PD to .docx file |
| `sanitize_filename` | Clean title for filesystem |
| `generate_filename` | Create filename from interview data |
| `get_export_path` | Build export path |

---

## RAG Tools (`src/tools/rag_tools.py`)

| Tool | Purpose |
|------|---------|
| `rag_lookup` | Query vector store for context |
| `format_rag_context` | Format retrieved docs for prompt |
| `answer_with_rag` | Answer HR questions with RAG |

---

## Unified Agent Tool Access

All tools are available to the unified agent via `ALL_TOOLS`:

```python
from src.agents.pd3r_agent import ALL_TOOLS, create_pd3r_agent

# ALL_TOOLS = INTERVIEW_TOOLS + KNOWLEDGE_TOOLS + DRAFTING_TOOLS + QA_TOOLS

agent = create_pd3r_agent()
# Agent can select any tool based on user input + phase context
```

**Phase-aware prompt** tells LLM which tools are most relevant:
- Interview phase → prioritize interview tools
- Drafting phase → prioritize drafting + QA tools
- QA phase → prioritize QA tools
- BUT knowledge tools (answer_user_question) always available

---

## Related Modules

- `src/config/fes_factors.py` — FES configuration
- `src/config/series_templates.py` — Duty templates
- `docs/business_rules/drafting_sections.py` — Section registry
- `src/models/draft.py` — DraftElement, QAReview models
- `src/models/requirements.py` — DraftRequirements model
