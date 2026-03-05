#!/usr/bin/env python3
"""E2E test runner for PD3r.

Runs the full agent flow with scripted inputs and validates expected behavior.
Can use either full or minimal interview configuration.

Usage:
    # Run with default (minimal) config
    poetry run python scripts/run_e2e_test.py

    # Run with full interview
    poetry run python scripts/run_e2e_test.py --full

    # Run with tracing enabled
    poetry run python scripts/run_e2e_test.py --trace

    # Verbose output
    poetry run python scripts/run_e2e_test.py -v
"""

import argparse
import asyncio
import json
import logging
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class TestResult:
    """Results from an e2e test run."""

    success: bool
    phases_completed: list[str] = field(default_factory=list)
    questions_asked: int = 0
    questions_answered: int = 0
    draft_elements_generated: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    final_state: dict[str, Any] | None = None

    def __str__(self) -> str:
        status = "✅ PASS" if self.success else "❌ FAIL"
        lines = [
            f"\n{'='*60}",
            f"E2E Test Result: {status}",
            f"{'='*60}",
            f"Duration: {self.duration_seconds:.2f}s",
            f"Phases completed: {', '.join(self.phases_completed) or 'none'}",
            f"Questions: {self.questions_answered}/{self.questions_asked} answered",
            f"Draft elements: {self.draft_elements_generated}",
        ]
        if self.errors:
            lines.append(f"\nErrors ({len(self.errors)}):")
            for err in self.errors[:5]:  # Show first 5
                lines.append(f"  - {err}")
        if self.warnings:
            lines.append(f"\nWarnings ({len(self.warnings)}):")
            for warn in self.warnings[:5]:
                lines.append(f"  - {warn}")
        lines.append("=" * 60)
        return "\n".join(lines)


class ScriptedInputProvider:
    """Provides scripted inputs for automated testing."""

    def __init__(
        self,
        answers: dict[str, str],
        default_confirmations: dict[str, str] | None = None,
        verbose: bool = False,
    ):
        """
        Initialize the input provider.

        Args:
            answers: Map of field_name -> answer value
            default_confirmations: Responses for yes/no prompts
            verbose: Whether to print each input
        """
        self.answers = answers
        self.confirmations = default_confirmations or {
            "confirm_interview": "yes",
            "approve_draft": "yes",
            "write_another": "no",
            "export_format": "markdown",
        }
        self.verbose = verbose
        self.input_log: list[tuple[str, str]] = []
        self._current_field: str | None = None

    def set_current_field(self, field_name: str) -> None:
        """Set which field we're answering."""
        self._current_field = field_name

    def get_input(self, prompt: str) -> str:
        """
        Get scripted input based on context from prompt.

        Args:
            prompt: The prompt text (used for context detection)

        Returns:
            Appropriate scripted response
        """
        prompt_lower = prompt.lower()
        response = ""

        # Check for explicit field answer
        if self._current_field and self._current_field in self.answers:
            response = self.answers[self._current_field]

        # Check confirmations
        elif "write another" in prompt_lower or "create another" in prompt_lower:
            response = self.confirmations.get("write_another", "no")
        elif "look correct" in prompt_lower or "everything look" in prompt_lower or "does this look" in prompt_lower:
            response = self.confirmations.get("confirm_interview", "yes")
        elif "approve" in prompt_lower or "acceptable" in prompt_lower:
            response = self.confirmations.get("approve_draft", "yes")
        elif "choose your export format" in prompt_lower or "export format" in prompt_lower:
            response = "done"
        elif "format" in prompt_lower and "export" in prompt_lower:
            response = "done"
        elif "export" in prompt_lower:
            response = "done"
        # Check for interview completion prompt
        elif "have everything" in prompt_lower or "review what we" in prompt_lower:
            response = "yes"
        # Handle "continue to next section" type prompts
        elif "continue" in prompt_lower and "section" in prompt_lower:
            response = "yes"
        # Handle "assemble the final document" prompt
        elif "assemble" in prompt_lower and "document" in prompt_lower:
            response = "yes"
        # Handle export retry prompts (when export fails)
        elif "different format" in prompt_lower or "try" in prompt_lower and "format" in prompt_lower:
            response = "done"

        # Fallback - try to match field name in prompt
        else:
            for field_name, answer in self.answers.items():
                field_readable = field_name.replace("_", " ")
                if field_readable in prompt_lower or field_name in prompt_lower:
                    response = answer
                    break

        # Default fallback - provide a reasonable generic answer
        if not response:
            # For fields we don't have answers for, provide generic data
            if self._current_field:
                # Generate a generic answer based on field name
                if "title" in self._current_field.lower():
                    response = "Project Manager"
                elif "organization" in self._current_field.lower():
                    response = "Department of Commerce, Bureau of Economic Analysis"
                elif "reports_to" in self._current_field.lower():
                    response = "Division Chief"
                elif "activities" in self._current_field.lower() or "duties" in self._current_field.lower():
                    response = "Lead projects 40%; Coordinate teams 30%; Report to leadership 30%"
                elif "supervisor" in self._current_field.lower():
                    response = "no"
                else:
                    response = f"Test data for {self._current_field}"
            elif any(word in prompt_lower for word in ["yes", "no", "correct", "ready"]):
                response = "yes"
            else:
                response = "continue"

        self.input_log.append((prompt[:50], response))
        if self.verbose:
            print(f"  [Script] '{prompt[:40]}...' -> '{response}'")

        return response


async def run_e2e_test(
    use_minimal: bool = True,
    trace: bool = False,
    verbose: bool = False,
    max_iterations: int = 100,
) -> TestResult:
    """
    Run end-to-end test with scripted inputs.

    Args:
        use_minimal: Use minimal interview config (faster)
        trace: Enable local tracing
        verbose: Verbose output
        max_iterations: Max loop iterations (safety)

    Returns:
        TestResult with pass/fail and metrics
    """
    import os
    import time

    if trace:
        os.environ["LOCAL_TRACING"] = "true"

    # Import after env setup
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.types import Command

    from src.graphs.main_graph import build_graph
    from src.utils.llm import is_tracing_enabled, start_run_trace, save_trace_log
    
    # Initialize tracing if enabled
    run_id = None
    if is_tracing_enabled():
        run_id = start_run_trace()

    # Load test config
    if use_minimal:
        from src.config.test_config import MINIMAL_INTAKE_SEQUENCE, TEST_ANSWERS

        answers = TEST_ANSWERS.copy()
        expected_questions = len(MINIMAL_INTAKE_SEQUENCE)
    else:
        from src.config.intake_fields import BASE_INTAKE_SEQUENCE
        from src.config.test_config import FULL_TEST_ANSWERS

        answers = FULL_TEST_ANSWERS.copy()
        expected_questions = len(BASE_INTAKE_SEQUENCE)
    
    # Add generic answers for any fields we might not have covered
    generic_answers = {
        "organization_hierarchy": "Department of Commerce, Bureau of Economic Analysis, Data Division",
        "reports_to": "Chief Data Officer",
        "daily_activities": "Analyze datasets, Build models, Create reports, Present findings",
        "major_duties": "Lead analytics 40%; Model development 35%; Stakeholder briefings 25%",
        "is_supervisor": "no",
    }
    # Merge generic answers (don't override explicit ones)
    for key, val in generic_answers.items():
        if key not in answers:
            answers[key] = val

    input_provider = ScriptedInputProvider(answers=answers, verbose=verbose)
    result = TestResult(success=False)
    start_time = time.time()

    try:
        # Build graph with memory checkpointer
        builder = build_graph()
        checkpointer = MemorySaver()
        graph = builder.compile(checkpointer=checkpointer)

        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        if verbose:
            print(f"\n🧪 Starting E2E test (minimal={use_minimal})")
            print(f"   Thread: {thread_id}")
            print(f"   Expected questions: {expected_questions}\n")

        initial_input: dict | Command | None = {}  # Empty dict to start graph
        iterations = 0
        last_phase = None

        while iterations < max_iterations:
            iterations += 1
            current_state = None

            # Stream graph execution
            async for event in graph.astream(initial_input, config, stream_mode="values"):
                current_state = event

                # Track phase transitions
                phase = event.get("phase", "unknown")
                if phase != last_phase:
                    result.phases_completed.append(phase)
                    last_phase = phase
                    if verbose:
                        print(f"  📍 Phase: {phase}")

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
                result.questions_asked += 1

                # Detect which field we're asking about
                current_field = None
                if current_state:
                    current_field = current_state.get("current_field")

                # Always update the current field (None clears it)
                input_provider.set_current_field(current_field)

                if verbose and prompt:
                    field_info = f" (field: {current_field})" if current_field else ""
                    print(f"  ❓ Q{result.questions_asked}{field_info}: {prompt[:60]}...")

                # Get scripted response
                user_input = input_provider.get_input(prompt)
                result.questions_answered += 1

                # Resume with input
                initial_input = Command(resume=user_input)

            else:
                # No interrupt - check for end state
                if current_state and current_state.get("should_end"):
                    wants_another = current_state.get("wants_another")
                    if wants_another is False:
                        if verbose:
                            print("  ✅ Conversation ended normally")
                        break
                    elif wants_another is None:
                        # Still need to process
                        initial_input = None
                        continue
                else:
                    # Unexpected completion
                    result.warnings.append(
                        f"Graph completed unexpectedly at iteration {iterations}"
                    )
                    break

        # Capture final state
        if current_state:
            result.final_state = dict(current_state)
            result.draft_elements_generated = len(
                current_state.get("draft_elements", [])
            )

        # Validate results
        if iterations >= max_iterations:
            result.errors.append(f"Hit max iterations ({max_iterations})")
        elif result.questions_answered < expected_questions:
            result.warnings.append(
                f"Fewer questions than expected: {result.questions_answered} < {expected_questions}"
            )

        # Check that we got through key phases
        required_phases = ["init", "interview"]
        for phase in required_phases:
            if phase not in result.phases_completed:
                result.errors.append(f"Missing required phase: {phase}")

        result.success = len(result.errors) == 0

    except Exception as e:
        result.errors.append(f"Exception: {type(e).__name__}: {str(e)}")
        if verbose:
            import traceback

            traceback.print_exc()

    finally:
        result.duration_seconds = time.time() - start_time
        # Save trace logs if tracing was enabled
        if is_tracing_enabled():
            trace_result = save_trace_log()
            if trace_result:
                jsonl_path, readable_path = trace_result
                if verbose:
                    print(f"\n📊 Trace saved:")
                    print(f"   JSONL: {jsonl_path}")
                    print(f"   Readable: {readable_path}")

    return result


def main() -> int:
    """Main entry point for e2e test runner."""
    parser = argparse.ArgumentParser(
        description="Run PD3r end-to-end tests with scripted inputs"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Use full interview (slower, more comprehensive)",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Enable local tracing (writes to output/logs/)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output showing each question/answer",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=100,
        help="Maximum loop iterations (safety limit)",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s: %(message)s",
    )

    # Run test
    result = asyncio.run(
        run_e2e_test(
            use_minimal=not args.full,
            trace=args.trace,
            verbose=args.verbose,
            max_iterations=args.max_iterations,
        )
    )

    print(result)

    # Save result to file
    output_path = Path("output/logs/e2e_test_result.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(
            {
                "success": result.success,
                "phases_completed": result.phases_completed,
                "questions_asked": result.questions_asked,
                "questions_answered": result.questions_answered,
                "draft_elements_generated": result.draft_elements_generated,
                "errors": result.errors,
                "warnings": result.warnings,
                "duration_seconds": result.duration_seconds,
            },
            f,
            indent=2,
        )
    print(f"\nResults saved to: {output_path}")

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
