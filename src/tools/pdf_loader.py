"""PDF loading and text chunking utilities for RAG."""

import os
from pathlib import Path
from typing import Iterator

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


# Default configuration
DEFAULT_CHUNK_SIZE = 1000  # ~500-1000 tokens
DEFAULT_CHUNK_OVERLAP = 100
KNOWLEDGE_DIR = Path(__file__).parent.parent.parent / "knowledge" / "unprocessed_pdfs"


def load_pdf(file_path: str | Path) -> list[Document]:
    """
    Load a single PDF file and return documents.

    Args:
        file_path: Path to the PDF file

    Returns:
        List of Document objects (one per page)
    """
    loader = PyPDFLoader(str(file_path))
    return loader.load()


def load_all_pdfs(
    directory: str | Path | None = None,
) -> list[Document]:
    """
    Load all PDF files from a directory.

    Args:
        directory: Path to directory containing PDFs.
                   Defaults to knowledge/unprocessed_pdfs/

    Returns:
        List of all Document objects from all PDFs
    """
    if directory is None:
        directory = KNOWLEDGE_DIR

    directory = Path(directory)
    if not directory.exists():
        raise FileNotFoundError(f"Knowledge directory not found: {directory}")

    documents: list[Document] = []
    pdf_files = list(directory.glob("*.pdf"))

    if not pdf_files:
        print(f"Warning: No PDF files found in {directory}")
        return documents

    for pdf_file in pdf_files:
        try:
            docs = load_pdf(pdf_file)
            # Add source metadata
            for doc in docs:
                doc.metadata["source_file"] = pdf_file.name
            documents.extend(docs)
            print(f"Loaded {len(docs)} pages from {pdf_file.name}")
        except Exception as e:
            print(f"Error loading {pdf_file.name}: {e}")

    print(f"Total documents loaded: {len(documents)}")
    return documents


def chunk_documents(
    documents: list[Document],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Document]:
    """
    Split documents into smaller chunks for embedding.

    Args:
        documents: List of documents to chunk
        chunk_size: Target size of each chunk in characters (~500-1000 tokens)
        chunk_overlap: Number of characters to overlap between chunks

    Returns:
        List of chunked Document objects
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks = text_splitter.split_documents(documents)
    print(f"Split {len(documents)} documents into {len(chunks)} chunks")
    return chunks


def load_and_chunk_pdfs(
    directory: str | Path | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Document]:
    """
    Load all PDFs from a directory and split into chunks.

    Convenience function that combines load_all_pdfs and chunk_documents.

    Args:
        directory: Path to directory containing PDFs
        chunk_size: Target size of each chunk in characters
        chunk_overlap: Number of characters to overlap between chunks

    Returns:
        List of chunked Document objects ready for embedding
    """
    documents = load_all_pdfs(directory)
    if not documents:
        return []
    return chunk_documents(documents, chunk_size, chunk_overlap)
