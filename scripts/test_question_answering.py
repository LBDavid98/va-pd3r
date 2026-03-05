#!/usr/bin/env python3
"""Test question answering (RAG and process questions) with intent classification.

This script tests the ask_question intent and answer_question node by:
1. Starting a conversation
2. Asking various questions (HR/RAG and process questions)
3. NOT completing the interview
4. Ending with quit to analyze the trace

Usage:
    poetry run python scripts/test_question_answering.py
    poetry run python scripts/test_question_answering.py --trace  # with tracing
    poetry run python scripts/test_question_answering.py -v       # verbose
"""

import argparse
import asyncio
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class QuestionTestResult:
    """Results from question answering test."""
    
    success: bool
    questions_sent: int = 0
    questions_answered: int = 0
    rag_questions: int = 0
    process_questions: int = 0
    intents_detected: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    
    def __str__(self) -> str:
        status = "✅ PASS" if self.success else "❌ FAIL"
        lines = [
            f"\n{'='*60}",
            f"Question Answering Test: {status}",
            f"{'='*60}",
            f"Duration: {self.duration_seconds:.2f}s",
            f"Questions sent: {self.questions_sent}",
            f"Questions answered: {self.questions_answered}",
            f"RAG questions: {self.rag_questions}",
            f"Process questions: {self.process_questions}",
            f"Intents detected: {', '.join(set(self.intents_detected))}",
        ]
        if self.errors:
            lines.append(f"\nErrors ({len(self.errors)}):")
            for err in self.errors[:5]:
                lines.append(f"  - {err}")
        lines.append("=" * 60)
        return "\n".join(lines)


# Test questions organized by type
TEST_QUESTIONS = [
    # Phase 1: Opening question
    ("Hello, what exactly is a position description?", "opening"),
    
    # Phase 2: HR/RAG Questions (should trigger RAG lookup)
    ("What is FES and how does it work?", "hr_rag"),
    ("How are GS grades determined?", "hr_rag"),
    ("Can you explain Factor 1 - Knowledge Required by the Position?", "hr_rag"),
    ("What's the difference between a GS-12 and GS-13?", "hr_rag"),
    
    # Phase 3: Process Questions (should NOT trigger RAG)
    ("What information do you need from me to create a PD?", "process"),
    ("How long does this process usually take?", "process"),
    ("Can I go back and change answers later?", "process"),
    
    # Phase 4: Mixed intent - Question while providing info
    ("I want to create a GS-13 IT Specialist position. What series code should I use?", "mixed"),
    ("That sounds right, but what does series 2210 actually cover?", "mixed"),
    
    # Phase 5: Edge cases
    ("What's a duty?", "edge"),
    ("What do you mean by that?", "edge"),
    ("Where are we in the process?", "edge"),
    
    # Phase 6: More HR questions
    ("What additional factors apply to supervisory positions?", "hr_rag"),
    ("What does OPM say about major duties in a PD?", "hr_rag"),
    
    # Final question before quit
    ("What happens if position requirements change after the PD is written?", "hr_rag"),
]


async def run_question_test(
    trace: bool = False,
    verbose: bool = False,
    max_questions: int | None = None,
) -> QuestionTestResult:
    """
    Run question answering test.
    
    Args:
        trace: Enable local tracing
        verbose: Verbose output
        max_questions: Limit number of questions (None = all)
    
    Returns:
        QuestionTestResult with metrics
    """
    if trace:
        os.environ["LOCAL_TRACING"] = "true"
    
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.types import Command
    
    from src.graphs.main_graph import build_graph
    from src.utils.llm import is_tracing_enabled, start_run_trace, save_trace_log
    
    # Initialize tracing
    if is_tracing_enabled():
        start_run_trace()
    
    result = QuestionTestResult(success=False)
    start_time = time.time()
    
    questions = TEST_QUESTIONS[:max_questions] if max_questions else TEST_QUESTIONS
    
    try:
        builder = build_graph()
        checkpointer = MemorySaver()
        graph = builder.compile(checkpointer=checkpointer)
        
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}
        
        if verbose:
            print(f"\n🧪 Question Answering Test")
            print(f"   Thread: {thread_id}")
            print(f"   Questions to ask: {len(questions)}\n")
        
        # Start with empty input to initialize
        initial_input: dict | Command | None = {}
        question_index = 0
        
        while question_index <= len(questions):
            current_state = None
            
            # Stream graph execution
            async for event in graph.astream(initial_input, config, stream_mode="values"):
                current_state = event
            
            # Check for interrupts
            state = await graph.aget_state(config)
            
            interrupt_value = None
            if state.tasks:
                for task in state.tasks:
                    if hasattr(task, "interrupts") and task.interrupts:
                        for interrupt in task.interrupts:
                            interrupt_value = interrupt.value
                            break
            
            if interrupt_value:
                prompt = interrupt_value.get("prompt", "")
                
                if verbose:
                    # Show agent's prompt (truncated)
                    print(f"  🤖 Pete: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
                
                # Get next question or quit
                if question_index < len(questions):
                    question, q_type = questions[question_index]
                    result.questions_sent += 1
                    
                    if q_type == "hr_rag":
                        result.rag_questions += 1
                    elif q_type == "process":
                        result.process_questions += 1
                    
                    if verbose:
                        print(f"\n  👤 User [{question_index + 1}/{len(questions)}] ({q_type}): {question}")
                    
                    initial_input = Command(resume=question)
                    question_index += 1
                else:
                    # All questions asked, send quit
                    if verbose:
                        print(f"\n  👤 User: quit")
                    initial_input = Command(resume="quit")
                    question_index += 1  # Increment to exit loop
                
            else:
                # No interrupt - check if conversation ended
                if current_state and current_state.get("should_end"):
                    if verbose:
                        print("  ✅ Conversation ended")
                    break
                else:
                    # Unexpected - continue anyway
                    initial_input = None
            
            # Track intent from state
            if current_state:
                intent = current_state.get("last_intent")
                if intent:
                    result.intents_detected.append(intent)
                    if intent == "ask_question":
                        result.questions_answered += 1
        
        result.success = result.questions_sent > 0
        
    except Exception as e:
        result.errors.append(f"Exception: {type(e).__name__}: {str(e)}")
        if verbose:
            import traceback
            traceback.print_exc()
    
    finally:
        result.duration_seconds = time.time() - start_time
        
        # Save trace
        if is_tracing_enabled():
            trace_result = save_trace_log()
            if trace_result:
                jsonl_path, readable_path = trace_result
                if verbose:
                    print(f"\n📊 Trace saved:")
                    print(f"   JSONL: {jsonl_path}")
                    print(f"   Readable: {readable_path}")
                print(f"\nAnalyze with: poetry run anode {jsonl_path}")
    
    return result


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test question answering and intent classification"
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Enable local tracing (writes to output/logs/)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--max-questions",
        type=int,
        default=None,
        help="Limit number of questions to ask",
    )
    
    args = parser.parse_args()
    
    result = asyncio.run(
        run_question_test(
            trace=args.trace,
            verbose=args.verbose,
            max_questions=args.max_questions,
        )
    )
    
    print(result)
    
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
