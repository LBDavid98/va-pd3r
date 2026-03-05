"""Vector store utilities for RAG."""

import os
from pathlib import Path
from typing import Optional

from langchain_chroma import Chroma
from langchain_core.documents import Document

from src.tools.embeddings import get_embeddings


# Default paths
KNOWLEDGE_BASE_DIR = Path(__file__).parent.parent.parent / "knowledge"
VECTOR_STORE_DIR = KNOWLEDGE_BASE_DIR / "vector_store"
COLLECTION_NAME = "pd3r_knowledge"


def get_vector_store(
    persist_directory: Optional[str | Path] = None,
    collection_name: str = COLLECTION_NAME,
) -> Chroma:
    """
    Get or create a Chroma vector store.

    Args:
        persist_directory: Directory to persist the vector store.
                          Defaults to knowledge/vector_store/
        collection_name: Name of the collection

    Returns:
        Configured Chroma vector store
    """
    if persist_directory is None:
        persist_directory = VECTOR_STORE_DIR

    persist_directory = Path(persist_directory)
    persist_directory.mkdir(parents=True, exist_ok=True)

    embeddings = get_embeddings()

    return Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=str(persist_directory),
    )


def build_vector_store(
    documents: list[Document],
    persist_directory: Optional[str | Path] = None,
    collection_name: str = COLLECTION_NAME,
) -> Chroma:
    """
    Build a new vector store from documents.

    Warning: This will create a new collection, potentially overwriting existing data.

    Args:
        documents: List of documents to embed and store
        persist_directory: Directory to persist the vector store
        collection_name: Name of the collection

    Returns:
        Populated Chroma vector store
    """
    if persist_directory is None:
        persist_directory = VECTOR_STORE_DIR

    persist_directory = Path(persist_directory)
    persist_directory.mkdir(parents=True, exist_ok=True)

    embeddings = get_embeddings()

    print(f"Building vector store with {len(documents)} documents...")
    print(f"Persist directory: {persist_directory}")

    # Create from documents (this embeds and stores)
    vector_store = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        collection_name=collection_name,
        persist_directory=str(persist_directory),
    )

    print(f"Vector store built successfully with {len(documents)} chunks")
    return vector_store


def vector_store_exists(
    persist_directory: Optional[str | Path] = None,
) -> bool:
    """
    Check if a vector store exists at the given path.

    Args:
        persist_directory: Directory to check

    Returns:
        True if vector store exists and has data
    """
    if persist_directory is None:
        persist_directory = VECTOR_STORE_DIR

    persist_directory = Path(persist_directory)

    # Check if directory exists and has chroma files
    if not persist_directory.exists():
        return False

    # Check for chroma.sqlite3 (Chroma's data file)
    chroma_file = persist_directory / "chroma.sqlite3"
    return chroma_file.exists()


def query_vector_store(
    query: str,
    k: int = 4,
    persist_directory: Optional[str | Path] = None,
) -> list[Document]:
    """
    Query the vector store for relevant documents.

    Args:
        query: Query text to search for
        k: Number of results to return
        persist_directory: Directory where vector store is persisted

    Returns:
        List of most relevant Document objects
    """
    vector_store = get_vector_store(persist_directory)
    return vector_store.similarity_search(query, k=k)


def query_with_scores(
    query: str,
    k: int = 4,
    persist_directory: Optional[str | Path] = None,
) -> list[tuple[Document, float]]:
    """
    Query the vector store and return documents with similarity scores.

    Args:
        query: Query text to search for
        k: Number of results to return
        persist_directory: Directory where vector store is persisted

    Returns:
        List of (Document, score) tuples, sorted by relevance
    """
    vector_store = get_vector_store(persist_directory)
    return vector_store.similarity_search_with_score(query, k=k)
