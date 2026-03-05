"""PD3r entry point - CLI for Federal Position Description Agent."""

import asyncio
import argparse
import json
import logging
import os
import signal
import sys
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langgraph.types import Command, Interrupt

# Load environment variables from .env file
load_dotenv()

from src.graphs.export import export_graph
from src.utils.llm import is_tracing_enabled, start_run_trace, save_trace_log
from src.config.intake_fields import INTAKE_FIELDS


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Session file location
SESSION_DIR = Path("output/.sessions")
SESSION_FILE = SESSION_DIR / "current_session.json"
DB_PATH = SESSION_DIR / "checkpoints.db"


def display_interview_progress(state: dict) -> None:
    """Display current interview progress - what's collected and what's missing.
    
    Shows a clean progress summary after each interaction during the interview phase.
    
    Args:
        state: Current agent state dict
    """
    phase = state.get("phase", "init")
    if phase not in ("interview", "requirements"):
        return  # Only show progress during interview/requirements phases
    
    interview_data = state.get("interview_data", {})
    missing_fields = state.get("missing_fields", [])
    needs_confirmation = state.get("fields_needing_confirmation", [])
    
    # Collect what's been gathered
    collected = []
    for field_name, element in interview_data.items():
        if isinstance(element, dict) and element.get("value") is not None:
            field_def = INTAKE_FIELDS.get(field_name)
            display_name = field_name.replace("_", " ").title()
            value = element["value"]
            
            # Format value for display
            if isinstance(value, dict):
                value_str = ", ".join(f"{k}: {v}" for k, v in value.items())
            elif isinstance(value, list):
                value_str = ", ".join(str(v) for v in value)
            elif isinstance(value, bool):
                value_str = "Yes" if value else "No"
            else:
                value_str = str(value)
            
            # Truncate long values
            if len(value_str) > 50:
                value_str = value_str[:47] + "..."
            
            collected.append(f"  ✓ {display_name}: {value_str}")
    
    # Format missing fields
    missing = []
    for field_name in missing_fields:
        display_name = field_name.replace("_", " ").title()
        missing.append(f"  ○ {display_name}")
    
    # Format fields needing confirmation
    confirm = []
    for field_name in needs_confirmation:
        display_name = field_name.replace("_", " ").title()
        confirm.append(f"  ⚠️  {display_name} (needs confirmation)")
    
    # Build the progress display
    print("\n" + "─" * 50)
    print("📋 Interview Progress")
    print("─" * 50)
    
    if collected:
        print("\n✅ Collected:")
        for item in collected:
            print(item)
    
    if confirm:
        print("\n⚠️  Needs Confirmation:")
        for item in confirm:
            print(item)
    
    if missing:
        print("\n📝 Remaining:")
        for item in missing:
            print(item)
    else:
        print("\n✨ All fields collected!")
    
    print("─" * 50 + "\n")


def get_session_info() -> dict[str, Any] | None:
    """Load existing session info from disk."""
    if SESSION_FILE.exists():
        try:
            with open(SESSION_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load session file: {e}")
    return None


def save_session_info(thread_id: str, position_title: str | None = None) -> None:
    """Save session info to disk."""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    info = {
        "thread_id": thread_id,
        "position_title": position_title,
    }
    with open(SESSION_FILE, "w") as f:
        json.dump(info, f)


def clear_session_info() -> None:
    """Clear the session file."""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


def prompt_resume_or_new(session_info: dict) -> bool:
    """Ask user whether to resume existing session or start fresh."""
    title = session_info.get("position_title")
    if title:
        print(f"\n📋 Found existing session: \"{title}\"")
    else:
        print("\n📋 Found existing session in progress.")
    
    while True:
        response = input("Resume? (y/n): ").strip().lower()
        if response in ("y", "yes"):
            return True
        elif response in ("n", "no"):
            return False
        print("Please enter 'y' or 'n'.")


async def run_agent() -> None:
    """
    Run the agent chat loop.
    
    Uses SQLite checkpointer for persistent sessions and handles
    the interrupt-resume pattern for user input collection.
    
    Tracing is controlled via PD3R_TRACING environment variable.
    """
    # Import here to avoid circular imports and allow tracing setup
    from langgraph.checkpoint.memory import MemorySaver
    from src.graphs.main_graph import build_graph
    
    # Ensure session directory exists
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    
    # Check for existing session
    session_info = get_session_info()
    thread_id: str
    is_resume = False
    
    if session_info:
        if prompt_resume_or_new(session_info):
            thread_id = session_info["thread_id"]
            is_resume = True
            print("\n🔄 Resuming session...\n")
        else:
            # Start fresh - generate new thread ID
            thread_id = str(uuid.uuid4())
            clear_session_info()
            save_session_info(thread_id)
            print("\n🆕 Starting new session...\n")
    else:
        # No existing session - start fresh
        thread_id = str(uuid.uuid4())
        save_session_info(thread_id)
    
    config = {"configurable": {"thread_id": thread_id}}
    
    # Initialize tracing if enabled
    run_id = None
    if is_tracing_enabled():
        run_id = start_run_trace()
        logger.info(f"Tracing started with run ID: {run_id}")
    
    # Use MemorySaver for checkpointing (temporary fix for aiosqlite compatibility)
    checkpointer = MemorySaver()
    
    # Build and compile graph with checkpointer
    builder = build_graph()
    graph = builder.compile(checkpointer=checkpointer)
    
    # Set up graceful exit handling
    shutdown_requested = False
    
    def handle_shutdown(signum: int, frame: Any) -> None:
        nonlocal shutdown_requested
        shutdown_requested = True
        print("\n\n👋 Saving session and exiting... Press Ctrl+C again to force quit.")
        # Save trace immediately on Ctrl+C
        if is_tracing_enabled():
            result = save_trace_log()
            if result:
                jsonl_path, readable_path = result
                print(f"📊 Trace saved: {readable_path}")
        # Re-register to allow force quit
        signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    signal.signal(signal.SIGINT, handle_shutdown)
    
    try:
        # Determine initial input
        if is_resume:
            # Resume: pass None to continue from checkpoint, then set is_resume flag
            # First, get current state to check if we're mid-interrupt
            current_state = await checkpointer.aget(config)
            if current_state:
                # We have saved state - invoke with None to continue
                # But we need to trigger init with is_resume flag
                initial_input: dict | Command | None = {"is_resume": True}
            else:
                # No state yet - treat as new
                initial_input = {}
        else:
            initial_input = {}
        
        # Main conversation loop
        while not shutdown_requested:
            # Stream graph execution
            result = None
            interrupt_value = None
            
            async for event in graph.astream(initial_input, config, stream_mode="values"):
                result = event
                # Extract position title for session tracking
                if "interview_data" in event:
                    interview_data = event.get("interview_data", {})
                    title = interview_data.get("position_title", {}).get("value")
                    if title:
                        save_session_info(thread_id, title)
            
            # Display interview progress after each turn
            if result:
                display_interview_progress(result)
            
            # Check for interrupts (user input needed)
            state = await graph.aget_state(config)
            
            if state.tasks:
                # Check for interrupt in tasks
                for task in state.tasks:
                    if hasattr(task, 'interrupts') and task.interrupts:
                        for interrupt in task.interrupts:
                            interrupt_value = interrupt.value
                            break
            
            if interrupt_value:
                # Display the prompt from the interrupt
                prompt = interrupt_value.get("prompt", "")
                if prompt:
                    print(f"\n🤖 Pete: {prompt}")
                
                # Check if conversation should end
                if result and result.get("should_end"):
                    wants_another = result.get("wants_another")
                    if wants_another is False:
                        print("\n✅ Session complete. Goodbye!")
                        clear_session_info()
                        break
                
                # Get user input
                try:
                    user_input = input("\n👤 You: ").strip()
                except EOFError:
                    # Handle piped input ending
                    print("\n👋 End of input. Saving session...")
                    break
                
                if not user_input:
                    print("(Please enter a response)")
                    continue
                
                # Resume with user input
                initial_input = Command(resume=user_input)
            else:
                # No interrupt - check if we've reached the end
                if result and result.get("should_end"):
                    wants_another = result.get("wants_another")
                    if wants_another is False:
                        print("\n✅ Session complete. Goodbye!")
                        clear_session_info()
                        break
                    elif wants_another is None:
                        # Need to ask about writing another - continue loop
                        initial_input = None
                    else:
                        # wants_another is True - restart will happen
                        initial_input = None
                else:
                    # Unexpected state - shouldn't reach here normally
                    logger.warning("Graph completed without interrupt or end state")
                    break
                    
    except KeyboardInterrupt:
        print("\n\n👋 Session saved. Run again to resume.")
    except Exception as e:
        logger.error(f"Error during conversation: {e}", exc_info=True)
        print(f"\n❌ An error occurred: {e}")
        print("Session has been saved. Run again to resume.")
        raise
    finally:
        # Save trace logs if tracing was enabled
        if is_tracing_enabled():
            result = save_trace_log()
            if result:
                jsonl_path, readable_path = result
                print(f"\n📊 Trace saved:")
                print(f"   JSONL: {jsonl_path}")
                print(f"   Readable: {readable_path}")


def main() -> None:
    """Main entry point for PD3r (Pete)."""
    parser = argparse.ArgumentParser(
        description="PD3r (Pete) - Federal Position Description Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  pd3r                  Start or resume a conversation
  pd3r --export-graph   Export graph visualization and exit
  pd3r --new            Start a new session (ignore existing)
  
  Enable tracing: PD3R_TRACING=true pd3r
        """,
    )
    parser.add_argument(
        "--export-graph",
        action="store_true",
        help="Export graph visualization and exit",
    )
    parser.add_argument(
        "--new",
        action="store_true",
        help="Start a new session (ignore any existing session)",
    )
    args = parser.parse_args()

    # Handle graph export
    if args.export_graph:
        from src.graphs import pd_graph
        mmd_path, png_path = export_graph(pd_graph, "output/graphs", "main_graph")
        print(f"📈 Graph exported:")
        print(f"   Mermaid: {mmd_path}")
        if png_path:
            print(f"   PNG: {png_path}")
        return

    # Clear session if --new flag
    if args.new:
        clear_session_info()
        print("🆕 Starting fresh session...")

    # Print banner
    print("\n" + "=" * 50)
    print("🤖 PD3r (Pete) - Federal Position Description Agent")
    print("=" * 50)
    print("\nType your responses at the prompt. Press Ctrl+C to save and exit.\n")

    # Run the agent
    try:
        asyncio.run(run_agent())
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
