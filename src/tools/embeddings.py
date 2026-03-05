"""Embedding utilities for RAG."""

import os
from functools import lru_cache
from typing import Optional

from langchain_openai import OpenAIEmbeddings


# Default embedding model
DEFAULT_EMBEDDING_MODEL = os.getenv(
    "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
)


@lru_cache(maxsize=1)
def get_embeddings(
    model: Optional[str] = None,
) -> OpenAIEmbeddings:
    """
    Get a configured OpenAI embeddings instance.

    Uses caching to return the same instance for efficiency.

    Args:
        model: Embedding model name. Defaults to text-embedding-3-small

    Returns:
        Configured OpenAIEmbeddings instance

    Raises:
        ValueError: If OPENAI_API_KEY is not set
    """
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError(
            "OPENAI_API_KEY environment variable is required for embeddings"
        )

    return OpenAIEmbeddings(
        model=model or DEFAULT_EMBEDDING_MODEL,
    )


def embed_query(text: str, model: Optional[str] = None) -> list[float]:
    """
    Embed a single query text.

    Args:
        text: Text to embed
        model: Optional model override

    Returns:
        Embedding vector as list of floats
    """
    embeddings = get_embeddings(model)
    return embeddings.embed_query(text)


def embed_documents(texts: list[str], model: Optional[str] = None) -> list[list[float]]:
    """
    Embed multiple documents.

    Args:
        texts: List of texts to embed
        model: Optional model override

    Returns:
        List of embedding vectors
    """
    embeddings = get_embeddings(model)
    return embeddings.embed_documents(texts)
