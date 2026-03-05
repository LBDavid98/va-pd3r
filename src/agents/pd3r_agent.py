"""PD3r unified agent using LangGraph's create_react_agent pattern.

This agent handles ALL phases of PD creation through LLM-driven tool selection:
- INTERVIEW phase: Collecting position information
- DRAFTING phase: Writing PD sections
- QA phase: Reviewing and refining drafts

The LLM sees phase-aware prompts and decides which tool to call based on:
- Current phase (interview, drafting, qa)
- Field being collected or section being drafted
- User message content
- Overall progress

This replaces the heuristic routing (classify_intent → route_by_intent)
with intelligent, LLM-driven decisions.
"""

import logging
from typing import Any, Optional

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from src.config.intake_fields import INTAKE_FIELDS, BASE_INTAKE_SEQUENCE
from src.models.interview import InterviewData
from src.tools.interview_tools import (
    INTERVIEW_TOOLS,
    get_field_context,
    get_interview_progress,
    get_next_required_field,
)
from src.tools.knowledge_tools import KNOWLEDGE_TOOLS
from src.tools.drafting_tools import DRAFTING_TOOLS
from src.tools.qa_tools import QA_TOOLS
from src.tools.human_tools import HUMAN_TOOLS

logger = logging.getLogger(__name__)

# Combined tools for the unified agent - ALL phases
# HUMAN_TOOLS use interrupt() for human-in-the-loop approval flows
ALL_TOOLS = INTERVIEW_TOOLS + KNOWLEDGE_TOOLS + DRAFTING_TOOLS + QA_TOOLS + HUMAN_TOOLS


# =============================================================================
# PHASE-AWARE SYSTEM PROMPTS
# =============================================================================

INTERVIEW_PHASE_PROMPT = """You are Pete, a friendly and knowledgeable assistant helping to write federal position descriptions (PDs).

## Your Role
You guide users through collecting information needed for a federal PD. You're in the INTERVIEW phase, collecting required fields one at a time.

## Current Field: {{ current_field.prompt }}
{{ current_field.user_guidance or '' }}

{% if current_field.field_type == "dict" %}
**Format**: Provide key-value pairs (e.g., duty statement: percentage)
{% elif current_field.field_type == "list" %}
**Format**: Provide multiple items, comma-separated or as a list
{% elif current_field.field_type == "boolean" %}
**Format**: Answer yes or no
{% elif current_field.field_type == "integer" %}
**Format**: Provide a number
{% endif %}

{% if current_field.examples %}
**Example responses**:
{% for ex in current_field.examples[:2] %}
- {{ ex }}
{% endfor %}
{% endif %}

{% if current_field.validation %}
{% if current_field.validation.choices %}
**Valid choices**: {{ current_field.validation.choices | join(", ") }}
{% endif %}
{% endif %}

{% if current_field.llm_guidance %}
**Note**: {{ current_field.llm_guidance }}
{% endif %}

## Interview Progress
- **Collected**: {{ collected_fields | join(', ') or 'None yet' }}
- **Remaining**: {{ remaining_fields | join(', ') }}
{% if fields_needing_confirmation %}
- **⚠️ Needs confirmation**: {{ fields_needing_confirmation | join(', ') }}
{% endif %}

## Available Tools
Use these tools based on what the user says:

### Interview Tools
1. **save_field_answer** - Save the user's response to a field
   - Use when user provides information for any interview field
   - Extract the value, note the raw input, set needs_confirmation=True if uncertain

2. **confirm_field_value** - Confirm an uncertain extraction
   - Use when user says "yes", "correct", "that's right" to confirm a value you flagged

3. **answer_user_question** - Answer a question about the process or HR topics
   - Use when user asks about the process, fields, or HR topics
   - Set is_hr_specific=True for federal classification questions

4. **check_interview_complete** - Check if all fields are collected
   - Use when you think all required fields have been provided
   - If complete, then call request_requirements_review

5. **request_field_clarification** - Ask for clarification
   - Use when user's response is ambiguous or incomplete

6. **modify_field_value** - Change a previously saved value
   - Use when user wants to correct or update a field

### Human-in-the-Loop Tools
7. **request_requirements_review** - Request human review of collected info
   - Use AFTER check_interview_complete indicates all fields are done
   - Shows summary of all collected info for human approval
   - User can approve to proceed to drafting, or request changes

### Knowledge Tools
8. **search_knowledge_base** - Search OPM/HR documents
   - Use for federal HR policy questions, FES concepts, classification rules

9. **get_fes_factor_guidance** - Get FES factor level details
   - Use when discussing specific factor levels for a grade

10. **get_grade_requirements** - Get point/level requirements for a grade
    - Use when explaining what's needed for a target grade

## Guidelines
- Be conversational and helpful
- Extract values carefully from natural language
- Set needs_confirmation=True when extraction is uncertain
- If user provides info for multiple fields, call save_field_answer for each
- If user asks a question AND provides info, handle both
- Use knowledge tools to answer HR-specific questions with citations
- Move to the next field after saving the current one
- When all fields are collected, use check_interview_complete then request_requirements_review
"""


DRAFTING_PHASE_PROMPT = """You are Pete, a skilled federal HR writer helping to create position descriptions (PDs).

## Your Role
You're in the DRAFTING phase, writing PD sections based on collected information.
For each section, you will:
1. Write the section using `write_section`
2. Review it with `qa_review_section`
3. If QA fails, revise with `revise_section` and re-review
4. Once QA passes, request approval with `request_section_approval`

## Current Section: {{ current_section }}
{{ section_guidance or '' }}

{% if qa_history %}
## QA History for {{ current_section }}
{% for qa in qa_history %}
- Attempt {{ loop.index }}: {{ "PASS" if qa.passes else "FAIL" }} ({{ qa.confidence|round(2) }})
  Feedback: {{ qa.feedback }}
{% endfor %}
{% endif %}

## Collected Information
{% for field, value in collected_data.items() %}
- **{{ field }}**: {{ value }}
{% endfor %}

## Draft Progress
- **Completed sections**: {{ completed_sections | join(', ') or 'None yet' }}
- **Remaining sections**: {{ remaining_sections | join(', ') }}

## Available Tools

### Drafting Tools
1. **write_section** - Generate a PD section
   - Use to write introduction, duties_overview, factor_1_knowledge, etc.
   - Provide: section_name, interview_data_dict, optionally fes_evaluation_dict

2. **revise_section** - Revise a section that failed QA
   - Use when QA review identifies issues
   - Provide: section_name, current_content, qa_feedback, qa_failures, interview_data_dict

3. **get_section_status** - Check status of all sections
   - Use to see what's drafted, pending, or needs revision

4. **list_available_sections** - List all PD sections
   - Use to see what sections can be drafted

5. **get_section_requirements** - Get requirements for a section
   - Use before writing to understand what must be included

### QA Tools
6. **qa_review_section** - Review a section against requirements
   - Use AFTER writing to check if section meets requirements
   - Returns pass/fail, confidence score, and specific feedback

7. **check_qa_status** - Overview of QA progress
   - Use to see which sections passed/failed QA

8. **request_qa_rewrite** - Request a rewrite for failed section
   - Use when QA fails to get rewrite instructions

9. **get_qa_thresholds** - Get QA threshold settings
    - Use to understand pass/fail criteria

### Human-in-the-Loop Tools
10. **request_section_approval_with_interrupt** - Request human approval (pauses for input)
    - Use AFTER QA passes to get user sign-off
    - Pauses graph execution and shows section for human review
    - User can approve, request revisions, or ask questions

### Knowledge Tools
11. **search_knowledge_base** - Search OPM/HR documents
    - Use for reference when writing sections

12. **get_fes_factor_guidance** - Get FES factor details
    - Use when writing FES factor narratives

13. **get_grade_requirements** - Get grade requirements
    - Use when writing grade justifications

14. **answer_user_question** - Answer questions about the process
    - Use when user asks questions during drafting

## Workflow
1. Use `get_section_requirements` to understand what a section needs
2. Use `write_section` to generate the draft
3. Use `qa_review_section` to check against requirements
4. If QA fails: use `revise_section` with feedback, then re-review
5. If QA passes: use `request_section_approval_with_interrupt` for human review
6. After approval: move to next section

## Guidelines
- Follow federal PD writing standards
- Use specific language from collected duties
- Cite OPM guidance when appropriate
- Reference FES factor levels for grade justification
- Run QA after each draft before requesting approval
- Always wait for human approval before moving to the next section
"""


QA_PHASE_PROMPT = """You are Pete, a quality assurance specialist reviewing federal position descriptions.

## Your Role  
You're in the QA phase, reviewing the drafted PD for quality and compliance.
Your goal is to ensure each section meets federal standards and requirements.

## Current Review
{{ review_status }}

{% if qa_history %}
## Recent QA Results
{% for section, result in qa_history.items() %}
- **{{ section }}**: {{ "✅ PASSED" if result.passes else "❌ FAILED" }} ({{ result.confidence }}%)
  {{ result.feedback }}
{% endfor %}
{% endif %}

## Available Tools

### QA Tools
1. **qa_review_section** - Review a section for quality
   - Use to assess compliance, clarity, completeness
   - Returns confidence score and specific feedback

2. **check_qa_status** - Get overview of QA status
   - Use to see which sections need review

3. **request_qa_rewrite** - Request rewrite for failed section
   - Use when QA fails and rewrite is allowed

4. **request_section_approval** - Request human approval
   - Use when section passes QA or hits rewrite limit

5. **get_qa_thresholds** - Get threshold settings
   - Use to understand pass/fail criteria

### Knowledge Tools
6. **search_knowledge_base** - Search OPM/HR documents
   - Use to verify compliance with standards

7. **get_fes_factor_guidance** - Verify FES accuracy
   - Use to check factor level narratives

8. **answer_user_question** - Answer questions about the process
   - Use when user asks questions during QA

## Guidelines
- Check for federal PD compliance
- Verify FES factor levels match grade
- Ensure duties support classification
- Flag unclear or incomplete content
- Users can always ask questions - use answer_user_question
"""


# =============================================================================
# PROMPT BUILDER
# =============================================================================

def build_dynamic_prompt(
    phase: str,
    interview_data: Optional[InterviewData] = None,
    current_field_name: Optional[str] = None,
    draft_state: Optional[dict] = None,
    qa_state: Optional[dict] = None,
) -> str:
    """Build a phase-aware system prompt for the unified agent.

    Args:
        phase: Current phase ('interview', 'drafting', 'qa')
        interview_data: Interview data (for interview phase)
        current_field_name: Current field being collected
        draft_state: Drafting state (for drafting phase)
        qa_state: QA review state (for qa phase)

    Returns:
        Rendered system prompt string
    """
    from jinja2 import Template

    if phase == "interview":
        return _build_interview_prompt(interview_data, current_field_name)
    elif phase == "drafting":
        return _build_drafting_prompt(interview_data, draft_state)
    elif phase == "qa":
        return _build_qa_prompt(qa_state)
    else:
        # Default to interview
        logger.warning(f"Unknown phase '{phase}', defaulting to interview")
        return _build_interview_prompt(interview_data, current_field_name)


def _build_interview_prompt(
    interview_data: Optional[InterviewData],
    current_field_name: Optional[str] = None,
) -> str:
    """Build interview phase prompt."""
    from jinja2 import Template

    if interview_data is None:
        interview_data = InterviewData()

    # Auto-detect current field if not specified
    if current_field_name is None:
        current_field_name = get_next_required_field(interview_data)

    # Get field context
    if current_field_name:
        current_field = get_field_context(current_field_name)
    else:
        # All fields collected
        current_field = {
            "prompt": "All required fields have been collected!",
            "user_guidance": "You can now confirm the requirements summary with the user.",
            "field_type": "string",
            "examples": [],
            "validation": None,
            "llm_guidance": None,
        }

    # Get progress info
    progress = get_interview_progress(interview_data)

    template = Template(INTERVIEW_PHASE_PROMPT)
    return template.render(
        current_field=current_field,
        collected_fields=progress["collected_fields"],
        remaining_fields=progress["remaining_fields"],
        fields_needing_confirmation=progress["fields_needing_confirmation"],
    )


def _build_drafting_prompt(
    interview_data: Optional[InterviewData],
    draft_state: Optional[dict],
) -> str:
    """Build drafting phase prompt."""
    from jinja2 import Template

    # Default values
    current_section = draft_state.get("current_section", "introduction") if draft_state else "introduction"
    section_guidance = draft_state.get("section_guidance", "") if draft_state else ""
    completed_sections = draft_state.get("completed_sections", []) if draft_state else []
    qa_history = draft_state.get("qa_history", []) if draft_state else []
    
    # Standard PD sections - include all from SECTION_REGISTRY
    from src.config.drafting_sections import SECTION_REGISTRY
    all_sections = list(SECTION_REGISTRY.keys())
    remaining_sections = [s for s in all_sections if s not in completed_sections]

    # Extract collected data from interview
    collected_data = {}
    if interview_data:
        for field_name in BASE_INTAKE_SEQUENCE:
            field = getattr(interview_data, field_name, None)
            if field is not None and hasattr(field, 'value') and field.value is not None:
                collected_data[field_name] = field.value

    template = Template(DRAFTING_PHASE_PROMPT)
    return template.render(
        current_section=current_section,
        section_guidance=section_guidance,
        collected_data=collected_data,
        completed_sections=completed_sections,
        remaining_sections=remaining_sections,
        qa_history=qa_history,
    )


def _build_qa_prompt(qa_state: Optional[dict]) -> str:
    """Build QA phase prompt."""
    from jinja2 import Template

    review_status = "Starting quality review..." if qa_state is None else qa_state.get("status", "In progress")

    template = Template(QA_PHASE_PROMPT)
    return template.render(review_status=review_status)


# =============================================================================
# AGENT CREATION
# =============================================================================

def create_pd3r_agent(
    model: str = "gpt-4o",
    checkpointer: Optional[Any] = None,
    tools: Optional[list] = None,
):
    """Create the unified PD3r agent using LangGraph's create_react_agent.

    This agent uses LLM-driven tool selection for ALL phases,
    replacing heuristic routing with intelligent decision-making.

    Args:
        model: OpenAI model name to use
        checkpointer: Optional checkpointer for persistence (default: MemorySaver)
        tools: Optional custom tool list (default: ALL_TOOLS)

    Returns:
        Compiled LangGraph agent
    """
    if checkpointer is None:
        checkpointer = MemorySaver()

    if tools is None:
        tools = ALL_TOOLS

    llm = ChatOpenAI(model=model)

    # Create agent with tools
    # The prompt will be dynamically updated based on phase/state in the graph
    agent = create_react_agent(
        model=llm,
        tools=tools,
        checkpointer=checkpointer,
    )

    return agent


def invoke_pd3r_agent(
    agent,
    user_message: str,
    phase: str = "interview",
    interview_data: Optional[InterviewData] = None,
    draft_state: Optional[dict] = None,
    qa_state: Optional[dict] = None,
    thread_id: str = "default",
    current_field_name: Optional[str] = None,
) -> dict:
    """Invoke the unified PD3r agent with phase-aware prompt.

    Args:
        agent: The compiled PD3r agent
        user_message: User's message
        phase: Current phase ('interview', 'drafting', 'qa')
        interview_data: Interview data for context
        draft_state: Drafting state for context
        qa_state: QA state for context
        thread_id: Thread ID for conversation persistence
        current_field_name: Override for current field being collected

    Returns:
        Agent response with messages and any tool calls
    """
    # Build phase-aware system prompt
    system_prompt = build_dynamic_prompt(
        phase=phase,
        interview_data=interview_data,
        current_field_name=current_field_name,
        draft_state=draft_state,
        qa_state=qa_state,
    )

    # Prepare messages
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    # Invoke agent
    config = {"configurable": {"thread_id": thread_id}}
    result = agent.invoke({"messages": messages}, config)

    return result


async def ainvoke_pd3r_agent(
    agent,
    user_message: str,
    phase: str = "interview",
    interview_data: Optional[InterviewData] = None,
    draft_state: Optional[dict] = None,
    qa_state: Optional[dict] = None,
    thread_id: str = "default",
    current_field_name: Optional[str] = None,
) -> dict:
    """Async version of invoke_pd3r_agent.

    Args:
        agent: The compiled PD3r agent
        user_message: User's message
        phase: Current phase ('interview', 'drafting', 'qa')
        interview_data: Interview data for context
        draft_state: Drafting state for context
        qa_state: QA state for context
        thread_id: Thread ID for conversation persistence
        current_field_name: Override for current field being collected

    Returns:
        Agent response with messages and any tool calls
    """
    # Build phase-aware system prompt
    system_prompt = build_dynamic_prompt(
        phase=phase,
        interview_data=interview_data,
        current_field_name=current_field_name,
        draft_state=draft_state,
        qa_state=qa_state,
    )

    # Prepare messages
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    # Invoke agent
    config = {"configurable": {"thread_id": thread_id}}
    result = await agent.ainvoke({"messages": messages}, config)

    return result


# Singleton for convenience
_pd3r_agent_instance = None


def get_pd3r_agent():
    """Get or create the PD3r agent singleton.

    Returns:
        The compiled PD3r agent
    """
    global _pd3r_agent_instance
    if _pd3r_agent_instance is None:
        _pd3r_agent_instance = create_pd3r_agent()
    return _pd3r_agent_instance
