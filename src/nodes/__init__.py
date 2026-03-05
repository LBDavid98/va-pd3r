"""Node implementations for PD3r."""

from src.nodes.answer_question_node import answer_question_node, answer_question_node_async
from src.nodes.check_interview_complete_node import check_interview_complete_node
from src.nodes.end_conversation_node import end_conversation_node
from src.nodes.error_handler_node import error_handler_node, route_after_error
from src.nodes.evaluate_fes_factors_node import evaluate_fes_factors_node
from src.nodes.export_node import export_document_node
from src.nodes.finalize_node import (
    finalize_node,
    handle_element_revision_request,
)
from src.nodes.gather_draft_requirements_node import gather_draft_requirements_node
from src.nodes.generate_element_node import generate_element_node_sync as generate_element_node
from src.nodes.handle_revision_node import (
    advance_to_next_element_node,
    handle_draft_response_node,
)
from src.nodes.handle_write_another_node import handle_write_another_node
from src.nodes.init_node import init_node
from src.nodes.intent_classification_node import intent_classification_node
from src.nodes.map_answers_node import map_answers_node
from src.nodes.prepare_next_node import prepare_next_node
from src.nodes.qa_review_node import qa_review_node_sync as qa_review_node
from src.nodes.routing import (
    route_after_advance_element,
    route_after_draft_response,
    route_after_element_revision,
    route_after_end_conversation,
    route_after_export,
    route_after_finalize,
    route_after_generate_element,
    route_after_init,
    route_after_qa,
    route_by_intent,
    route_should_end,
)
from src.nodes.user_input_node import user_input_node

__all__ = [
    # Phase 1-2 nodes
    "answer_question_node",
    "answer_question_node_async",
    "check_interview_complete_node",
    "end_conversation_node",
    "error_handler_node",
    "init_node",
    "intent_classification_node",
    "map_answers_node",
    "prepare_next_node",
    "user_input_node",
    # Phase 3 nodes
    "evaluate_fes_factors_node",
    "gather_draft_requirements_node",
    "generate_element_node",
    "qa_review_node",
    "handle_draft_response_node",
    "advance_to_next_element_node",
    # Phase 4 nodes
    "finalize_node",
    "handle_element_revision_request",
    "handle_write_another_node",
    "export_document_node",
    # Routing
    "route_after_advance_element",
    "route_after_draft_response",
    "route_after_element_revision",
    "route_after_end_conversation",
    "route_after_error",
    "route_after_export",
    "route_after_finalize",
    "route_after_generate_element",
    "route_after_init",
    "route_by_intent",
    "route_should_end",
    "route_after_qa",
]
