"""Interview agent using LangGraph's create_react_agent pattern.

This agent uses LLM-driven tool selection instead of heuristic routing.
The LLM sees state-aware prompts and decides which tool to call based on:
- Current phase and field being collected
- User message content
- Interview progress

This replaces the _route_interview_phase() heuristic routing function.
"""

import logging
from typing import Any, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from src.config.intake_fields import INTAKE_FIELDS, BASE_INTAKE_SEQUENCE
from src.models.interview import InterviewData
from src.prompts import get_template
from src.tools.interview_tools import (
    INTERVIEW_TOOLS,
    get_field_context,
    get_interview_progress,
    get_next_required_field,
)

logger = logging.getLogger(__name__)

# Interview agent system prompt template
INTERVIEW_AGENT_SYSTEM_PROMPT = """You are Pete, a friendly and knowledgeable assistant helping to write federal position descriptions (PDs).

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

1. **save_field_answer** - Save the user's response to a field
   - Use when user provides information for any interview field
   - Extract the value, note the raw input, set needs_confirmation=True if uncertain

2. **confirm_field_value** - Confirm an uncertain extraction
   - Use when user says "yes", "correct", "that's right" to confirm a value you flagged

3. **answer_user_question** - Answer a question
   - Use when user asks about the process, fields, or HR topics
   - Set is_hr_specific=True for federal classification questions

4. **check_interview_complete** - Check if all fields are collected
   - Use when you think all required fields have been provided

5. **request_field_clarification** - Ask for clarification
   - Use when user's response is ambiguous or incomplete

6. **modify_field_value** - Change a previously saved value
   - Use when user wants to correct or update a field

## Guidelines
- Be conversational and helpful
- Extract values carefully from natural language
- Set needs_confirmation=True when extraction is uncertain
- If user provides info for multiple fields, call save_field_answer for each
- If user asks a question AND provides info, handle both
- Move to the next field after saving the current one
"""


def build_interview_prompt(
    interview_data: InterviewData,
    current_field_name: Optional[str] = None,
) -> str:
    """Build a state-aware system prompt for the interview agent.

    Args:
        interview_data: Current interview data with collected values
        current_field_name: Name of field currently being collected (or auto-detect)

    Returns:
        Rendered system prompt string
    """
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

    # Use Jinja2 for template rendering
    from jinja2 import Template

    template = Template(INTERVIEW_AGENT_SYSTEM_PROMPT)
    return template.render(
        current_field=current_field,
        collected_fields=progress["collected_fields"],
        remaining_fields=progress["remaining_fields"],
        fields_needing_confirmation=progress["fields_needing_confirmation"],
    )


def create_interview_agent(
    model: str = "gpt-4o",
    checkpointer: Optional[Any] = None,
):
    """Create the interview agent using LangGraph's create_react_agent.

    This agent uses LLM-driven tool selection for the interview phase,
    replacing heuristic routing with intelligent decision-making.

    Args:
        model: OpenAI model name to use
        checkpointer: Optional checkpointer for persistence (default: MemorySaver)

    Returns:
        Compiled LangGraph agent
    """
    if checkpointer is None:
        checkpointer = MemorySaver()

    llm = ChatOpenAI(model=model)

    # Create agent with tools
    # Note: The prompt will be dynamically updated based on state in the graph
    agent = create_react_agent(
        model=llm,
        tools=INTERVIEW_TOOLS,
        checkpointer=checkpointer,
    )

    return agent


def invoke_interview_agent(
    agent,
    user_message: str,
    interview_data: InterviewData,
    thread_id: str,
    current_field_name: Optional[str] = None,
) -> dict:
    """Invoke the interview agent with state-aware prompt.

    Args:
        agent: The compiled interview agent
        user_message: User's message
        interview_data: Current interview data
        thread_id: Thread ID for conversation persistence
        current_field_name: Override for current field being collected

    Returns:
        Agent response with messages and any tool calls
    """
    # Build state-aware system prompt
    system_prompt = build_interview_prompt(interview_data, current_field_name)

    # Prepare messages
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    # Invoke agent
    config = {"configurable": {"thread_id": thread_id}}
    result = agent.invoke({"messages": messages}, config)

    return result


async def ainvoke_interview_agent(
    agent,
    user_message: str,
    interview_data: InterviewData,
    thread_id: str,
    current_field_name: Optional[str] = None,
) -> dict:
    """Async version of invoke_interview_agent.

    Args:
        agent: The compiled interview agent
        user_message: User's message
        interview_data: Current interview data
        thread_id: Thread ID for conversation persistence
        current_field_name: Override for current field being collected

    Returns:
        Agent response with messages and any tool calls
    """
    # Build state-aware system prompt
    system_prompt = build_interview_prompt(interview_data, current_field_name)

    # Prepare messages
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    # Invoke agent
    config = {"configurable": {"thread_id": thread_id}}
    result = await agent.ainvoke({"messages": messages}, config)

    return result


# Convenience function to get the agent as a singleton
_interview_agent_instance = None


def get_interview_agent():
    """Get or create the interview agent singleton.

    Returns:
        The compiled interview agent
    """
    global _interview_agent_instance
    if _interview_agent_instance is None:
        _interview_agent_instance = create_interview_agent()
    return _interview_agent_instance
