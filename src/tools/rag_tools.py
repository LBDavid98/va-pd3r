"""RAG (Retrieval-Augmented Generation) tools for HR knowledge queries."""

import os
from typing import Any, Optional

from langchain_core.documents import Document

from src.tools.vector_store import (
    query_vector_store,
    query_with_scores,
    vector_store_exists,
)


def rag_lookup(
    query: str,
    k: int = 4,
    score_threshold: float = 0.0,
) -> list[tuple[Document, float]]:
    """
    Query the knowledge base for relevant documents.

    Args:
        query: The question or search query
        k: Number of results to return
        score_threshold: Minimum similarity score (0-1, higher is more similar).
                        Note: Chroma uses L2 distance, so lower scores are better.
                        Set to 0 to disable threshold filtering.

    Returns:
        List of (Document, score) tuples, sorted by relevance.
        Returns empty list if vector store doesn't exist.
    """
    if not vector_store_exists():
        print("Warning: Vector store not found. Run ingestion script first.")
        return []

    results = query_with_scores(query, k=k)

    # Filter by threshold if specified
    # Note: ChromaDB returns L2 distance where lower is better
    # A typical "good" score is < 1.0
    if score_threshold > 0:
        results = [(doc, score) for doc, score in results if score <= score_threshold]

    return results


def format_rag_context(
    results: list[tuple[Document, float]],
    max_chars: int = 4000,
) -> str:
    """
    Format RAG results into a context string for the LLM prompt.

    Args:
        results: List of (Document, score) tuples from rag_lookup
        max_chars: Maximum characters for context (to avoid token limits)

    Returns:
        Formatted string with source citations
    """
    if not results:
        return ""

    context_parts = []
    total_chars = 0

    for i, (doc, score) in enumerate(results, 1):
        source = doc.metadata.get("source_file", "Unknown source")
        page = doc.metadata.get("page", "?")
        content = doc.page_content.strip()

        # Check if adding this would exceed limit
        entry = f"[Source {i}: {source}, Page {page}]\n{content}\n"
        if total_chars + len(entry) > max_chars:
            break

        context_parts.append(entry)
        total_chars += len(entry)

    return "\n---\n".join(context_parts)


def get_source_citations(results: list[tuple[Document, float]]) -> list[str]:
    """
    Extract source citations from RAG results.

    Args:
        results: List of (Document, score) tuples

    Returns:
        List of source citation strings (e.g., "Classifier's Handbook, Page 12")
    """
    citations = []
    seen = set()

    for doc, _ in results:
        source = doc.metadata.get("source_file", "Unknown")
        page = doc.metadata.get("page", "?")
        citation = f"{source}, Page {page}"

        if citation not in seen:
            citations.append(citation)
            seen.add(citation)

    return citations


async def answer_with_rag(
    question: str,
    context: dict[str, Any],
    k: int = 4,
) -> tuple[str, list[str]]:
    """
    Answer a question using RAG-enhanced generation.

    Args:
        question: The user's question
        context: Additional context (interview_summary, phase, etc.)
        k: Number of documents to retrieve

    Returns:
        Tuple of (answer, citations)
    """
    from src.prompts import get_template
    from src.utils import get_chat_model

    # Retrieve relevant documents
    results = rag_lookup(question, k=k)

    if not results:
        # Fall back to non-RAG answer if no knowledge base
        return (
            "I don't have access to the OPM knowledge base right now. "
            "For specific HR policy questions, I'd recommend consulting "
            "your HR office or reviewing OPM.gov directly.",
            [],
        )

    # Format context
    rag_context = format_rag_context(results)
    citations = get_source_citations(results)

    # Build prompt
    template = get_template("rag_answer.jinja")
    prompt = template.render(
        question=question,
        rag_context=rag_context,
        citations=citations,
        **context,
    )

    # Get LLM response
    llm = get_chat_model()
    response = await llm.ainvoke(prompt)

    return response.content, citations
