"""Answer question node - handles user questions during the interview.

⚠️ ARCHITECTURE DECISION: NO MOCK/FALLBACK LLM IMPLEMENTATIONS ⚠️
This node MUST use real LLM calls. Do not add:
- Hardcoded response templates
- Pattern-matching fallbacks
- "answer_without_llm" functions
- Mock responses for testing

All question-answering requires LLM intelligence. Tests should use proper
LLM mocking at the API level, not application-level fallbacks.
See ADR in AGENTS.MD for rationale.

Includes error handling that routes to error_handler on LLM failures.
"""

import logging
import os
from typing import Any

from langchain_core.messages import AIMessage

from src.models.interview import InterviewData
from src.models.state import AgentState
from src.prompts import get_template
from src.utils.llm import get_chat_model, traced_llm_call, traced_node

logger = logging.getLogger(__name__)


def _build_interview_summary(state: AgentState) -> str:
    """
    Build a summary of collected interview data for context.

    Args:
        state: Current agent state

    Returns:
        Formatted summary string or empty string if no data
    """
    interview_dict = state.get("interview_data")
    if not interview_dict:
        return ""

    interview = InterviewData.model_validate(interview_dict)
    summary_dict = interview.to_summary_dict()

    if not summary_dict:
        return ""

    lines = []
    for field_name, value in summary_dict.items():
        friendly_name = field_name.replace("_", " ").title()
        if isinstance(value, list):
            value_str = ", ".join(str(v) for v in value)
        elif isinstance(value, dict):
            value_str = "; ".join(f"{k}: {v}" for k, v in value.items())
        elif isinstance(value, bool):
            value_str = "Yes" if value else "No"
        else:
            value_str = str(value)
        lines.append(f"- {friendly_name}: {value_str}")

    return "\n".join(lines)


async def answer_question_with_rag(
    question: str,
    state: AgentState,
) -> str:
    """
    Answer an HR-specific question using RAG (Retrieval-Augmented Generation).

    Queries the OPM knowledge base for relevant documents and uses them
    to generate an accurate, citation-backed answer.

    Args:
        question: The user's HR-specific question
        state: Current agent state for context

    Returns:
        RAG-enhanced answer with source citations
    """
    from src.tools.rag_tools import answer_with_rag

    # Build context
    context: dict[str, Any] = {
        "phase": state.get("phase", "interview"),
        "current_field": state.get("current_field"),
        "interview_summary": _build_interview_summary(state),
    }

    # Get RAG-enhanced answer
    answer, citations = await answer_with_rag(question, context, k=4)

    return answer


async def answer_question_with_llm(
    question: str,
    state: AgentState,
) -> str:
    """
    Answer the user's question using LLM (non-RAG).

    Used for process questions and general clarifications that don't
    need the OPM knowledge base.

    Args:
        question: The user's question
        state: Current agent state for context

    Returns:
        LLM-generated answer
    """
    # Build context
    context: dict[str, Any] = {
        "phase": state.get("phase", "interview"),
        "current_field": state.get("current_field"),
        "interview_summary": _build_interview_summary(state),
        "question": question,
    }

    # Render prompt
    template = get_template("answer_question.jinja")
    prompt = template.render(**context)

    # Get LLM
    llm = get_chat_model()

    # Call LLM with tracing
    response_content, _usage = await traced_llm_call(
        llm=llm,
        prompt=prompt,
        node_name="answer_question",
        metadata={"phase": context["phase"], "question": question[:100]},
    )
    return response_content


@traced_node
async def answer_question_node(state: AgentState) -> dict:
    """
    Answer user question using LLM (async version).

    Routes to RAG for HR-specific questions, regular LLM for other questions.
    Includes error handling that routes to error_handler on LLM failures.
    
    ⚠️ NO MOCK IMPLEMENTATIONS - This node requires real LLM calls.
    If the API key is missing, the node will raise an error rather than
    returning fake responses.

    Args:
        state: Current agent state with pending_question and intent

    Returns:
        State update with answer message
        
    Raises:
        RuntimeError: If required API key is not set
    """
    from src.models.intent import IntentClassification
    from src.tools.vector_store import vector_store_exists

    question = state.get("pending_question", "")

    if not question:
        return {
            "messages": [AIMessage(content="Is there something I can help clarify?")],
            "pending_question": None,
        }

    # Require API key - no fallbacks
    if not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        # This is a configuration error - route to error_handler
        logger.error("Missing API key for LLM")
        return {
            "last_error": "answer_question: ConfigurationError: LLM API key required. Set ANTHROPIC_API_KEY or OPENAI_API_KEY.",
            "messages": [AIMessage(content="I'm having trouble connecting to my AI backend.")],
            "pending_question": None,
        }

    # Check if this is an HR-specific question (from intent classification)
    is_hr_question = False
    intent_dict = state.get("intent_classification")
    if intent_dict:
        intent = IntentClassification.model_validate(intent_dict)
        is_hr_question = intent.is_hr_specific or False

    try:
        # Use RAG for HR questions if knowledge base exists
        if is_hr_question and vector_store_exists():
            answer = await answer_question_with_rag(question, state)
        else:
            answer = await answer_question_with_llm(question, state)

        # Update next_prompt so the interrupt shows the answer, not the stale prompt
        # The answer itself ends with a follow-up question to continue the interview
        return {
            "messages": [AIMessage(content=answer)],
            "pending_question": None,
            "next_prompt": answer,  # Show the answer at the interrupt
        }
    except Exception as e:
        # LLM or RAG error - route to error_handler
        logger.error(f"Error answering question: {e}", exc_info=True)
        error_msg = "I had trouble answering that question. Could you try asking it differently?"
        return {
            "last_error": f"answer_question: {type(e).__name__}: {str(e)}",
            "messages": [AIMessage(content=error_msg)],
            "pending_question": None,
            "next_prompt": error_msg,
        }


# Backwards-compatible alias for existing imports
answer_question_node_async = answer_question_node
