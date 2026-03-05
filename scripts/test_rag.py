#!/usr/bin/env python
"""Test RAG question answering functionality."""

import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

from src.models.intent import IntentClassification, Question
from src.nodes.answer_question_node import answer_question_node_async


async def test_rag_question():
    """Test answering an HR-specific question via RAG."""
    # Simulate state with a question
    state = {
        'phase': 'interview',
        'pending_question': 'What is Factor 1 in the FES?',
        'intent_classification': {
            'primary_intent': 'ask_question',
            'secondary_intents': [],
            'confidence': 0.95,
            'field_mappings': [],
            'questions': [
                {
                    'text': 'What is Factor 1 in the FES?',
                    'is_hr_specific': True,
                    'is_process_question': False
                }
            ],
            'modifications': [],
            'element_modifications': [],
            'export_request': None
        },
        'interview_data': {}
    }

    print("Testing RAG question answering...")
    result = await answer_question_node_async(state)
    
    print(f"\nResult keys: {list(result.keys())}")
    if result.get('messages'):
        content = result['messages'][0].content
        print(f"\nAnswer ({len(content)} chars):\n{content[:800]}...")
    else:
        print("No message in result!")


if __name__ == "__main__":
    asyncio.run(test_rag_question())
