"""Knowledge tools for LLM-driven question answering.

These tools wrap existing RAG and knowledge lookup functions as LangChain tools
so the agent can use them via tool selection.

ARCHITECTURE NOTE: This file wraps existing logic from:
- src/tools/rag_tools.py (RAG lookup functions)
- src/config/fes_factors.py (FES factor configuration)
- src/nodes/answer_question_node.py (question answering logic)

We do NOT rewrite this logic - we wrap it for tool access.
"""

import logging
from typing import Any

from langchain_core.tools import tool

from src.config.fes_factors import (
    FACTOR_NAMES,
    get_does_statements,
    get_factor_level_for_grade,
    get_factor_name,
    get_factor_points,
    get_grade_cutoff,
    parse_grade_number,
)
from src.tools.rag_tools import (
    format_rag_context,
    get_source_citations,
    rag_lookup,
)

logger = logging.getLogger(__name__)


@tool
def search_knowledge_base(query: str, num_results: int = 4) -> str:
    """Search the OPM/HR knowledge base for relevant information.

    Use this tool when the user asks about:
    - Federal HR policies and regulations
    - FES (Factor Evaluation System) concepts
    - Position classification rules
    - OPM guidelines and standards
    - Grade determination criteria

    Args:
        query: The search query - be specific about what you're looking for
        num_results: Number of results to return (default 4)

    Returns:
        Formatted context from relevant documents with source citations,
        or a message if no relevant documents are found.
    """
    logger.info(f"Tool search_knowledge_base: '{query[:50]}...' (k={num_results})")
    
    results = rag_lookup(query, k=num_results)
    
    if not results:
        return (
            "No relevant documents found in the knowledge base. "
            "For specific HR policy questions, recommend consulting "
            "your HR office or reviewing OPM.gov directly."
        )
    
    context = format_rag_context(results)
    citations = get_source_citations(results)
    
    if citations:
        citation_str = "\n\nSources: " + ", ".join(citations)
        return context + citation_str
    
    return context


@tool
def get_fes_factor_guidance(factor_number: int, target_grade: int) -> str:
    """Get FES factor level guidance for a specific factor and grade.

    Use this tool when discussing:
    - What level a factor should be for a given grade
    - What "does" statements apply to a factor level
    - Point values for factor levels
    - Factor definitions and descriptions

    Args:
        factor_number: Factor number 1-9 (e.g., 1 for Knowledge Required)
        target_grade: Target GS grade (9-15)

    Returns:
        Formatted guidance including factor name, target level, points, and does statements.
    """
    logger.info(f"Tool get_fes_factor_guidance: Factor {factor_number}, Grade {target_grade}")
    
    # Validate inputs
    if factor_number < 1 or factor_number > 9:
        return f"Invalid factor number {factor_number}. Valid range is 1-9."
    
    if target_grade < 9 or target_grade > 15:
        return f"Grade {target_grade} is outside supported range (9-15)."
    
    # Get factor info
    factor_name = get_factor_name(factor_number)
    target_level = get_factor_level_for_grade(target_grade, factor_number)
    
    if target_level is None:
        return f"No level data for Factor {factor_number} at GS-{target_grade}."
    
    # Format level code
    if factor_number == 7:
        level_code = f"{factor_number}-{target_level}"  # e.g., "7-c"
    else:
        level_code = f"{factor_number}-{target_level}"  # e.g., "1-7"
    
    # Get points
    points = get_factor_points(factor_number, target_level)
    
    # Get does statements
    does_statements = get_does_statements(factor_number, target_level)
    
    # Format response
    lines = [
        f"## Factor {factor_number}: {factor_name}",
        f"**Target Level for GS-{target_grade}:** {level_code}",
        f"**Points:** {points}",
        "",
        "**What the employee DOES at this level:**",
    ]
    
    if does_statements:
        for stmt in does_statements:
            lines.append(f"- {stmt}")
    else:
        lines.append("- No specific 'does' statements defined for this level.")
    
    return "\n".join(lines)


@tool
def get_grade_requirements(target_grade: int) -> str:
    """Get the FES point requirements and factor levels for a target grade.

    Use this tool when discussing:
    - What total points are needed for a grade
    - What factor levels are typical for a grade
    - Grade determination criteria

    Args:
        target_grade: Target GS grade (9-15)

    Returns:
        Formatted summary of point requirements and typical factor levels.
    """
    logger.info(f"Tool get_grade_requirements: GS-{target_grade}")
    
    if target_grade < 9 or target_grade > 15:
        return f"Grade {target_grade} is outside supported range (9-15)."
    
    cutoff = get_grade_cutoff(target_grade)
    if cutoff is None:
        return f"No cutoff data for GS-{target_grade}."
    
    lines = [
        f"## GS-{target_grade} Requirements",
        f"**Point Range:** {cutoff.min_points}" + 
        (f" - {cutoff.max_points}" if cutoff.max_points else "+"),
        "",
        "**Typical Factor Levels:**",
    ]
    
    for factor_num in range(1, 10):
        factor_name = get_factor_name(factor_num)
        level = get_factor_level_for_grade(target_grade, factor_num)
        if level is not None:
            if factor_num == 7:
                level_code = f"{factor_num}-{level}"
            else:
                level_code = f"{factor_num}-{level}"
            points = get_factor_points(factor_num, level)
            lines.append(f"- Factor {factor_num} ({factor_name}): Level {level_code} ({points} pts)")
    
    return "\n".join(lines)


# Export all knowledge tools for use in agent creation
KNOWLEDGE_TOOLS = [
    search_knowledge_base,
    get_fes_factor_guidance,
    get_grade_requirements,
]
