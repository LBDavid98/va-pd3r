#!/usr/bin/env python
"""
One-time ingestion script for building the RAG knowledge base.

Usage:
    poetry run python scripts/ingest_knowledge.py
    poetry run python scripts/ingest_knowledge.py --pdf-dir /path/to/pdfs
    poetry run python scripts/ingest_knowledge.py --rebuild  # Force rebuild

Prerequisites:
    1. Place PDF files in knowledge/unprocessed_pdfs/
    2. Ensure OPENAI_API_KEY is set in environment or .env file
"""

import argparse
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def main():
    parser = argparse.ArgumentParser(
        description="Build RAG vector store from PDF documents"
    )
    parser.add_argument(
        "--pdf-dir",
        type=str,
        help="Directory containing PDF files (default: knowledge/unprocessed_pdfs/)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Directory to store vector database (default: knowledge/vector_store/)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="Target chunk size in characters (default: 1000)",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=100,
        help="Overlap between chunks in characters (default: 100)",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Force rebuild even if vector store exists",
    )

    args = parser.parse_args()

    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable is required")
        print("Set it in your environment or in a .env file")
        sys.exit(1)

    # Import after path setup
    from src.tools.pdf_loader import load_and_chunk_pdfs
    from src.tools.vector_store import (
        VECTOR_STORE_DIR,
        build_vector_store,
        vector_store_exists,
    )

    # Determine directories
    pdf_dir = Path(args.pdf_dir) if args.pdf_dir else None
    output_dir = Path(args.output_dir) if args.output_dir else VECTOR_STORE_DIR

    # Check if vector store already exists
    if vector_store_exists(output_dir) and not args.rebuild:
        print(f"Vector store already exists at {output_dir}")
        print("Use --rebuild to force recreation")
        
        # Show stats
        from src.tools.vector_store import get_vector_store
        vs = get_vector_store(output_dir)
        count = vs._collection.count()
        print(f"Current document count: {count}")
        sys.exit(0)

    # Load and chunk PDFs
    print("\n=== Loading PDFs ===")
    chunks = load_and_chunk_pdfs(
        directory=pdf_dir,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )

    if not chunks:
        print("No documents to process. Add PDF files to knowledge/unprocessed_pdfs/")
        sys.exit(1)

    # Build vector store
    print("\n=== Building Vector Store ===")
    vector_store = build_vector_store(
        documents=chunks,
        persist_directory=output_dir,
    )

    # Verify
    print("\n=== Verification ===")
    count = vector_store._collection.count()
    print(f"Vector store created with {count} chunks")
    print(f"Location: {output_dir}")

    # Test query
    print("\n=== Test Query ===")
    test_query = "What is the Federal Evaluation System?"
    results = vector_store.similarity_search(test_query, k=2)
    print(f"Query: '{test_query}'")
    print(f"Found {len(results)} results")
    if results:
        print(f"Top result from: {results[0].metadata.get('source_file', 'unknown')}")
        print(f"Preview: {results[0].page_content[:200]}...")

    print("\n=== Done ===")
    print("Knowledge base is ready for RAG queries!")


if __name__ == "__main__":
    main()
