"""Tool implementations for PD3r."""

from src.tools.embeddings import embed_documents, embed_query, get_embeddings
from src.tools.export_tools import (
    DEFAULT_EXPORT_PATH,
    export_to_markdown,
    export_to_word,
    generate_filename,
    get_export_path,
    sanitize_filename,
)
from src.tools.interview_tools import (
    INTERVIEW_TOOLS,
    answer_user_question,
    check_interview_complete,
    confirm_field_value,
    get_field_context,
    get_interview_progress,
    get_next_required_field,
    modify_field_value,
    request_field_clarification,
    save_field_answer,
)
from src.tools.pdf_loader import (
    chunk_documents,
    load_all_pdfs,
    load_and_chunk_pdfs,
    load_pdf,
)
from src.tools.rag_tools import (
    answer_with_rag,
    format_rag_context,
    get_source_citations,
    rag_lookup,
)
from src.tools.vector_store import (
    build_vector_store,
    get_vector_store,
    query_vector_store,
    query_with_scores,
    vector_store_exists,
)
from src.tools.knowledge_tools import (
    KNOWLEDGE_TOOLS,
    get_fes_factor_guidance,
    get_grade_requirements,
    search_knowledge_base,
)
from src.tools.drafting_tools import (
    DRAFTING_TOOLS,
    get_section_requirements,
    get_section_status,
    list_available_sections,
    revise_section,
    write_section,
)
from src.tools.qa_tools import (
    QA_TOOLS,
    check_qa_status,
    get_qa_thresholds,
    qa_review_section,
    request_qa_rewrite,
    request_section_approval,
)
from src.tools.human_tools import (
    HUMAN_TOOLS,
    parse_approval_response,
    request_requirements_review,
    request_section_approval_with_interrupt,
)

__all__ = [
    # PDF Loader
    "load_pdf",
    "load_all_pdfs",
    "chunk_documents",
    "load_and_chunk_pdfs",
    # Embeddings
    "get_embeddings",
    "embed_query",
    "embed_documents",
    # Vector Store
    "get_vector_store",
    "build_vector_store",
    "vector_store_exists",
    "query_vector_store",
    "query_with_scores",
    # RAG Tools
    "rag_lookup",
    "format_rag_context",
    "get_source_citations",
    "answer_with_rag",
    # Export Tools
    "export_to_markdown",
    "export_to_word",
    "sanitize_filename",
    "generate_filename",
    "get_export_path",
    "DEFAULT_EXPORT_PATH",
    # Interview Tools (LLM-driven)
    "INTERVIEW_TOOLS",
    "save_field_answer",
    "confirm_field_value",
    "answer_user_question",
    "check_interview_complete",
    "request_field_clarification",
    "modify_field_value",
    "get_next_required_field",
    "get_field_context",
    "get_interview_progress",
    # Knowledge Tools (LLM-driven)
    "KNOWLEDGE_TOOLS",
    "search_knowledge_base",
    "get_fes_factor_guidance",
    "get_grade_requirements",
    # Drafting Tools (LLM-driven)
    "DRAFTING_TOOLS",
    "write_section",
    "revise_section",
    "get_section_status",
    "list_available_sections",
    "get_section_requirements",
    # QA Tools (LLM-driven)
    "QA_TOOLS",
    "qa_review_section",
    "check_qa_status",
    "request_qa_rewrite",
    "request_section_approval",
    "get_qa_thresholds",
    # Human-in-the-Loop Tools (interrupt-based)
    "HUMAN_TOOLS",
    "request_requirements_review",
    "request_section_approval_with_interrupt",
    "parse_approval_response",
]
