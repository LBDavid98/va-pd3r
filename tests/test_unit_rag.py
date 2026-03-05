"""Unit tests for RAG tools (mocked vector store)."""

import pytest
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document


class TestFormatRagContext:
    """Tests for format_rag_context function."""

    def test_empty_results_returns_empty_string(self):
        """Empty results should return empty string."""
        from src.tools.rag_tools import format_rag_context

        result = format_rag_context([])
        assert result == ""

    def test_single_result_formatted_correctly(self):
        """Single result should be formatted with source info."""
        from src.tools.rag_tools import format_rag_context

        doc = Document(
            page_content="This is test content.",
            metadata={"source_file": "test.pdf", "page": 1},
        )
        results = [(doc, 0.5)]

        result = format_rag_context(results)

        assert "[Source 1: test.pdf, Page 1]" in result
        assert "This is test content." in result

    def test_multiple_results_separated(self):
        """Multiple results should be separated by dividers."""
        from src.tools.rag_tools import format_rag_context

        docs = [
            Document(
                page_content="Content one.",
                metadata={"source_file": "doc1.pdf", "page": 1},
            ),
            Document(
                page_content="Content two.",
                metadata={"source_file": "doc2.pdf", "page": 5},
            ),
        ]
        results = [(docs[0], 0.3), (docs[1], 0.5)]

        result = format_rag_context(results)

        assert "[Source 1: doc1.pdf, Page 1]" in result
        assert "[Source 2: doc2.pdf, Page 5]" in result
        assert "---" in result  # Separator

    def test_max_chars_respected(self):
        """Should truncate if content exceeds max_chars."""
        from src.tools.rag_tools import format_rag_context

        doc = Document(
            page_content="A" * 1000,  # Long content
            metadata={"source_file": "test.pdf", "page": 1},
        )
        results = [(doc, 0.5)]

        result = format_rag_context(results, max_chars=100)

        # Should be empty because even one entry exceeds limit
        # (header + content > 100 chars)
        assert len(result) <= 100 or result == ""


class TestGetSourceCitations:
    """Tests for get_source_citations function."""

    def test_empty_results_returns_empty_list(self):
        """Empty results should return empty list."""
        from src.tools.rag_tools import get_source_citations

        result = get_source_citations([])
        assert result == []

    def test_extracts_unique_citations(self):
        """Should extract unique source citations."""
        from src.tools.rag_tools import get_source_citations

        docs = [
            Document(page_content="A", metadata={"source_file": "doc1.pdf", "page": 1}),
            Document(page_content="B", metadata={"source_file": "doc2.pdf", "page": 5}),
        ]
        results = [(docs[0], 0.3), (docs[1], 0.5)]

        citations = get_source_citations(results)

        assert "doc1.pdf, Page 1" in citations
        assert "doc2.pdf, Page 5" in citations
        assert len(citations) == 2

    def test_deduplicates_same_source_and_page(self):
        """Should deduplicate identical citations."""
        from src.tools.rag_tools import get_source_citations

        docs = [
            Document(page_content="A", metadata={"source_file": "doc1.pdf", "page": 1}),
            Document(page_content="B", metadata={"source_file": "doc1.pdf", "page": 1}),
        ]
        results = [(docs[0], 0.3), (docs[1], 0.5)]

        citations = get_source_citations(results)

        assert len(citations) == 1
        assert citations[0] == "doc1.pdf, Page 1"


class TestRagLookup:
    """Tests for rag_lookup function with mocked vector store."""

    def test_returns_empty_when_no_vector_store(self):
        """Should return empty list when vector store doesn't exist."""
        from src.tools.rag_tools import rag_lookup

        with patch("src.tools.rag_tools.vector_store_exists", return_value=False):
            results = rag_lookup("test query")
            assert results == []

    def test_queries_vector_store_when_exists(self):
        """Should query vector store when it exists."""
        from src.tools.rag_tools import rag_lookup

        mock_doc = Document(
            page_content="FES Factor 1 is Knowledge Required.",
            metadata={"source_file": "handbook.pdf", "page": 10},
        )

        with patch("src.tools.rag_tools.vector_store_exists", return_value=True):
            with patch(
                "src.tools.rag_tools.query_with_scores",
                return_value=[(mock_doc, 0.5)],
            ) as mock_query:
                results = rag_lookup("What is Factor 1?", k=4)

                mock_query.assert_called_once_with("What is Factor 1?", k=4)
                assert len(results) == 1
                assert results[0][0].page_content == "FES Factor 1 is Knowledge Required."


class TestChunkDocuments:
    """Tests for document chunking."""

    def test_splits_long_document(self):
        """Should split long documents into chunks."""
        from src.tools.pdf_loader import chunk_documents

        long_content = "This is a sentence. " * 100  # ~2000 chars
        doc = Document(page_content=long_content, metadata={"source": "test"})

        chunks = chunk_documents([doc], chunk_size=500, chunk_overlap=50)

        # Should have multiple chunks
        assert len(chunks) > 1
        # Each chunk should be <= chunk_size (roughly)
        for chunk in chunks:
            assert len(chunk.page_content) <= 600  # Allow some flexibility

    def test_preserves_metadata(self):
        """Chunks should preserve source metadata."""
        from src.tools.pdf_loader import chunk_documents

        doc = Document(
            page_content="Short content that won't be split.",
            metadata={"source_file": "test.pdf", "page": 5},
        )

        chunks = chunk_documents([doc], chunk_size=1000)

        assert len(chunks) >= 1
        assert chunks[0].metadata["source_file"] == "test.pdf"


class TestQuestionIntegration:
    """Tests for HR question detection in intent classification."""

    def test_is_hr_specific_detected_for_fes_question(self):
        """FES-related questions should be marked as HR-specific."""
        from src.models.intent import IntentClassification, Question

        intent = IntentClassification(
            primary_intent="ask_question",
            confidence=0.9,
            questions=[
                Question(
                    text="What is Factor 1 in the FES system?",
                    is_hr_specific=True,
                    is_process_question=False,
                )
            ],
        )

        assert intent.is_hr_specific is True
        assert intent.has_questions is True

    def test_is_hr_specific_false_for_process_question(self):
        """Process questions should not be marked as HR-specific."""
        from src.models.intent import IntentClassification, Question

        intent = IntentClassification(
            primary_intent="ask_question",
            confidence=0.9,
            questions=[
                Question(
                    text="How does this process work?",
                    is_hr_specific=False,
                    is_process_question=True,
                )
            ],
        )

        assert intent.is_hr_specific is False
        assert intent.is_process_question is True

    def test_no_questions_returns_none(self):
        """is_hr_specific should be None when no questions."""
        from src.models.intent import IntentClassification

        intent = IntentClassification(
            primary_intent="provide_information",
            confidence=0.9,
        )

        assert intent.is_hr_specific is None
        assert intent.has_questions is False
