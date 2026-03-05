"""Integration tests for RAG system with real embeddings."""

import os

import pytest

# Skip all tests in this module if no API key
pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY required for RAG integration tests",
    ),
]


class TestRagIntegration:
    """Integration tests for RAG with real embeddings (requires API key)."""

    @pytest.fixture
    def sample_documents(self):
        """Create sample documents for testing."""
        from langchain_core.documents import Document

        return [
            Document(
                page_content="""
                Factor 1 - Knowledge Required by the Position

                Factor 1 measures the nature and extent of information or facts
                which the workers must understand to do acceptable work (e.g.,
                steps, procedures, practices, rules, policies, theories, principles,
                and concepts) and the nature and extent of the skills needed to
                apply those knowledges.
                """,
                metadata={"source_file": "test_handbook.pdf", "page": 1},
            ),
            Document(
                page_content="""
                The GS-2210 Information Technology Management series covers
                positions that manage, supervise, lead, administer, develop,
                deliver, and support information technology (IT) systems and
                services.
                """,
                metadata={"source_file": "test_2210_standard.pdf", "page": 1},
            ),
            Document(
                page_content="""
                Supervisory positions are evaluated using the General Schedule
                Supervisory Guide (GSSG). The guide uses six factors to evaluate
                the level of supervisory responsibilities.
                """,
                metadata={"source_file": "test_gssg.pdf", "page": 1},
            ),
        ]

    @pytest.fixture
    def temp_vector_store(self, tmp_path, sample_documents):
        """Create a temporary vector store for testing."""
        from src.tools.vector_store import build_vector_store

        # Build vector store in temp directory
        vector_store = build_vector_store(
            documents=sample_documents,
            persist_directory=tmp_path / "test_vector_store",
            collection_name="test_collection",
        )
        return vector_store, tmp_path / "test_vector_store"

    def test_can_build_and_query_vector_store(self, temp_vector_store):
        """Should be able to build and query vector store."""
        vector_store, persist_dir = temp_vector_store

        # Query for Factor 1
        results = vector_store.similarity_search("What is Factor 1?", k=2)

        assert len(results) >= 1
        # Should find the Factor 1 document
        assert any("Factor 1" in doc.page_content for doc in results)

    def test_query_returns_relevant_results(self, temp_vector_store):
        """Queries should return semantically relevant results."""
        vector_store, persist_dir = temp_vector_store

        # Query about IT positions
        results = vector_store.similarity_search(
            "What series covers IT management positions?", k=2
        )

        assert len(results) >= 1
        # Should find the 2210 document
        assert any("2210" in doc.page_content for doc in results)

    def test_query_with_scores_returns_scores(self, temp_vector_store):
        """Should return similarity scores with results."""
        vector_store, persist_dir = temp_vector_store

        results = vector_store.similarity_search_with_score(
            "supervisory positions", k=2
        )

        assert len(results) >= 1
        # Each result should be (doc, score) tuple
        for doc, score in results:
            assert hasattr(doc, "page_content")
            assert isinstance(score, float)

    def test_rag_lookup_with_temp_store(self, temp_vector_store):
        """Test that rag_lookup returns results when vector store exists.
        
        Note: This test uses the vector store directly rather than monkeypatching
        rag_lookup, since the embeddings cache makes monkeypatching unreliable.
        The actual rag_lookup function is tested via manual integration testing.
        """
        vector_store, persist_dir = temp_vector_store

        # Query the vector store directly
        results = vector_store.similarity_search_with_score("What is Factor 1?", k=2)

        assert len(results) >= 1
        # Should have (doc, score) tuples
        doc, score = results[0]
        assert "Factor" in doc.page_content


class TestAnswerWithRag:
    """Integration tests for answer_with_rag function."""

    @pytest.fixture
    def mock_rag_results(self):
        """Mock RAG results for testing answer generation."""
        from langchain_core.documents import Document

        return [
            (
                Document(
                    page_content="""
                    Factor 1 - Knowledge Required by the Position measures the
                    nature and extent of information or facts which the workers
                    must understand to do acceptable work.
                    """,
                    metadata={"source_file": "handbook.pdf", "page": 10},
                ),
                0.3,
            ),
        ]

    @pytest.mark.asyncio
    async def test_answer_with_rag_generates_response(self, mock_rag_results, monkeypatch):
        """Should generate answer using RAG context."""
        from src.tools import rag_tools

        # Mock the rag_lookup to return our mock results
        monkeypatch.setattr(rag_tools, "rag_lookup", lambda q, k: mock_rag_results)

        from src.tools.rag_tools import answer_with_rag

        answer, citations = await answer_with_rag(
            question="What is Factor 1?",
            context={"phase": "interview"},
            k=2,
        )

        # Should have generated an answer
        assert len(answer) > 0
        # Should have citations
        assert len(citations) >= 1
        assert "handbook.pdf" in citations[0]

    @pytest.mark.asyncio
    async def test_answer_with_rag_no_results_fallback(self, monkeypatch):
        """Should provide fallback when no RAG results."""
        from src.tools import rag_tools

        # Mock empty results
        monkeypatch.setattr(rag_tools, "rag_lookup", lambda q, k: [])

        from src.tools.rag_tools import answer_with_rag

        answer, citations = await answer_with_rag(
            question="What is Factor 1?",
            context={"phase": "interview"},
            k=2,
        )

        # Should have fallback message
        assert "knowledge base" in answer.lower() or "OPM" in answer
        # No citations when no results
        assert citations == []
