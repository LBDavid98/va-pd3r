#!/usr/bin/env python3
"""agentscript - Automated Agent Conversation Runner.

Run scripted conversations against your LangGraph agent for testing,
benchmarking, and trace generation.

Usage:
    agentscript <script_file>              Run a conversation script
    agentscript <script_file> --stream     Stream responses in real-time
    agentscript --create <name>            Create a new script template
    agentscript --list                     List available scripts

Examples:
    agentscript scripts/test_interview.txt --stream -v 2
    agentscript scripts/edge_cases.txt --verbose

Script Format:
    Each line is a user message sent to the agent.
    Lines starting with # are comments.
    Lines starting with @PAUSE wait for Enter key.
    Lines starting with @WAIT:<seconds> add a delay.
    Lines starting with @EXPECT:<text> assert response contains text.
    Empty lines are ignored.
    The conversation ends automatically after the last message.
"""

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

# Add parent to path for imports when run directly
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent_toolkit.core.config import ToolkitConfig, get_config, set_config


# =============================================================================
# ANSI Color Codes for Beautiful Output
# =============================================================================

class Colors:
    """ANSI color codes for terminal output."""
    
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"
    
    # Foreground
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    
    # Bright foreground
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"
    
    # Background
    BG_BLACK = "\033[40m"
    BG_BLUE = "\033[44m"
    BG_GREEN = "\033[42m"
    
    @classmethod
    def disable(cls):
        """Disable colors (for non-TTY output)."""
        for attr in dir(cls):
            if not attr.startswith("_") and isinstance(getattr(cls, attr), str):
                setattr(cls, attr, "")


# Disable colors if not a TTY
if not sys.stdout.isatty():
    Colors.disable()


# =============================================================================
# Script Parser
# =============================================================================

class ScriptCommand:
    """A single command in a script."""
    
    def __init__(
        self,
        command_type: str,
        content: str,
        line_number: int,
        original_line: str,
    ):
        self.command_type = command_type  # 'message', 'pause', 'wait', 'expect', 'comment'
        self.content = content
        self.line_number = line_number
        self.original_line = original_line


def parse_script(script_path: Path) -> list[ScriptCommand]:
    """Parse a script file into commands.
    
    Args:
        script_path: Path to the script file
        
    Returns:
        List of ScriptCommand objects
    """
    commands = []
    
    with open(script_path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.rstrip("\n\r")
            stripped = line.strip()
            
            # Skip empty lines
            if not stripped:
                continue
            
            # Comments
            if stripped.startswith("#"):
                commands.append(ScriptCommand("comment", stripped[1:].strip(), line_num, line))
                continue
            
            # Special commands
            if stripped.startswith("@PAUSE"):
                commands.append(ScriptCommand("pause", "", line_num, line))
                continue
            
            if stripped.startswith("@WAIT:"):
                try:
                    seconds = float(stripped[6:])
                    commands.append(ScriptCommand("wait", str(seconds), line_num, line))
                except ValueError:
                    commands.append(ScriptCommand("message", line, line_num, line))
                continue
            
            if stripped.startswith("@EXPECT:"):
                expected = stripped[8:].strip()
                commands.append(ScriptCommand("expect", expected, line_num, line))
                continue
            
            if stripped.upper() == "@END":
                commands.append(ScriptCommand("end", "", line_num, line))
                continue
            
            # Regular message
            commands.append(ScriptCommand("message", line, line_num, line))
    
    return commands


# =============================================================================
# Output Formatting
# =============================================================================

class OutputFormatter:
    """Beautiful output formatting for agent conversations."""
    
    def __init__(self, verbosity: int = 1):
        """Initialize formatter.
        
        Args:
            verbosity: 0=quiet, 1=normal, 2=verbose, 3=debug
        """
        self.verbosity = verbosity
        self.start_time = time.time()
        self.message_count = 0
        self.total_tokens = 0
        self.total_cost = 0.0
    
    def print_header(self, script_name: str, total_commands: int):
        """Print script header."""
        if self.verbosity < 1:
            return
        
        print()
        print(f"{Colors.BOLD}{Colors.CYAN}╔{'═' * 58}╗{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  🤖 AGENTSCRIPT - Automated Conversation Runner          {Colors.BOLD}{Colors.CYAN}║{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}╠{'═' * 58}╣{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  Script: {Colors.WHITE}{script_name:<47}{Colors.RESET} {Colors.BOLD}{Colors.CYAN}║{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  Commands: {Colors.WHITE}{total_commands:<45}{Colors.RESET} {Colors.BOLD}{Colors.CYAN}║{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  Started: {Colors.WHITE}{datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<46}{Colors.RESET} {Colors.BOLD}{Colors.CYAN}║{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}╚{'═' * 58}╝{Colors.RESET}")
        print()
    
    def print_user_message(self, message: str, index: int):
        """Print a user message."""
        self.message_count += 1
        
        print(f"{Colors.BRIGHT_BLACK}───────────────────────────────────────────────────────────{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.GREEN}👤 USER [{index}]{Colors.RESET}")
        print(f"{Colors.GREEN}{message}{Colors.RESET}")
        print()
    
    def print_agent_response(self, response: str, tokens: int = 0, cost: float = 0.0):
        """Print an agent response."""
        self.total_tokens += tokens
        self.total_cost += cost
        
        print(f"{Colors.BOLD}{Colors.BLUE}🤖 AGENT{Colors.RESET}", end="")
        if self.verbosity >= 2 and (tokens or cost):
            print(f" {Colors.DIM}({tokens} tokens, ${cost:.4f}){Colors.RESET}", end="")
        print()
        print(f"{Colors.BLUE}{response}{Colors.RESET}")
        print()
    
    def print_streaming_start(self):
        """Print streaming indicator."""
        print(f"{Colors.BOLD}{Colors.BLUE}🤖 AGENT{Colors.RESET} ", end="", flush=True)
    
    def print_streaming_chunk(self, chunk: str):
        """Print a streaming chunk."""
        print(f"{Colors.BLUE}{chunk}{Colors.RESET}", end="", flush=True)
    
    def print_streaming_end(self, tokens: int = 0, cost: float = 0.0):
        """Print end of streaming."""
        self.total_tokens += tokens
        self.total_cost += cost
        
        if self.verbosity >= 2 and (tokens or cost):
            print(f" {Colors.DIM}({tokens} tokens, ${cost:.4f}){Colors.RESET}")
        else:
            print()
        print()
    
    def print_comment(self, comment: str):
        """Print a script comment."""
        if self.verbosity >= 2:
            print(f"{Colors.DIM}# {comment}{Colors.RESET}")
    
    def print_pause(self):
        """Print pause indicator."""
        print(f"\n{Colors.YELLOW}⏸️  PAUSED - Press Enter to continue...{Colors.RESET}", end="", flush=True)
    
    def print_wait(self, seconds: float):
        """Print wait indicator."""
        if self.verbosity >= 1:
            print(f"{Colors.DIM}⏳ Waiting {seconds}s...{Colors.RESET}")
    
    def print_expect_result(self, expected: str, found: bool):
        """Print expectation result."""
        if found:
            print(f"{Colors.GREEN}✓ Expected text found: '{expected[:40]}...'{Colors.RESET}")
        else:
            print(f"{Colors.RED}✗ Expected text NOT found: '{expected[:40]}...'{Colors.RESET}")
    
    def print_error(self, error: str):
        """Print an error."""
        print(f"{Colors.RED}❌ ERROR: {error}{Colors.RESET}")
    
    def print_footer(self, success: bool, failed_expects: int = 0):
        """Print script footer."""
        if self.verbosity < 1:
            return
        
        elapsed = time.time() - self.start_time
        
        print()
        print(f"{Colors.BRIGHT_BLACK}{'═' * 60}{Colors.RESET}")
        
        status_color = Colors.GREEN if success else Colors.RED
        status_text = "COMPLETED" if success else "FAILED"
        
        print(f"{Colors.BOLD}Script {status_color}{status_text}{Colors.RESET}")
        print(f"  Messages: {self.message_count}")
        print(f"  Duration: {elapsed:.1f}s")
        if self.total_tokens:
            print(f"  Tokens:   {self.total_tokens:,}")
        if self.total_cost:
            print(f"  Cost:     ${self.total_cost:.4f}")
        if failed_expects:
            print(f"  {Colors.RED}Failed expectations: {failed_expects}{Colors.RESET}")
        print()


# =============================================================================
# Script Runner
# =============================================================================

class ScriptRunner:
    """Runs agent conversation scripts."""
    
    def __init__(
        self,
        config: ToolkitConfig | None = None,
        stream: bool = False,
        verbosity: int = 1,
    ):
        """Initialize script runner.
        
        Args:
            config: Toolkit configuration
            stream: Whether to stream responses
            verbosity: Output verbosity level
        """
        self.config = config or get_config()
        self.stream = stream
        self.formatter = OutputFormatter(verbosity)
        self.verbosity = verbosity
        self.paused = False
        self.last_response = ""
        self.failed_expects = 0
    
    async def run_script(
        self,
        script_path: Path,
        agent_runner: Callable[[str], Any] | None = None,
    ) -> bool:
        """Run a conversation script.
        
        Args:
            script_path: Path to the script file
            agent_runner: Optional custom function to run agent.
                          Should accept a string message and return response.
                          If None, will try to import and use project's graph.
                          
        Returns:
            True if all expectations passed, False otherwise
        """
        if not script_path.exists():
            self.formatter.print_error(f"Script not found: {script_path}")
            return False
        
        commands = parse_script(script_path)
        self.formatter.print_header(script_path.name, len(commands))
        
        # Get or create agent runner
        if agent_runner is None:
            agent_runner = await self._create_default_runner()
            if agent_runner is None:
                self.formatter.print_error("Could not create agent runner")
                return False
        
        # Run commands
        message_index = 0
        for cmd in commands:
            if cmd.command_type == "comment":
                self.formatter.print_comment(cmd.content)
                continue
            
            if cmd.command_type == "pause":
                self.formatter.print_pause()
                input()  # Wait for Enter
                continue
            
            if cmd.command_type == "wait":
                seconds = float(cmd.content)
                self.formatter.print_wait(seconds)
                await asyncio.sleep(seconds)
                continue
            
            if cmd.command_type == "expect":
                found = cmd.content.lower() in self.last_response.lower()
                self.formatter.print_expect_result(cmd.content, found)
                if not found:
                    self.failed_expects += 1
                continue
            
            if cmd.command_type == "end":
                break
            
            if cmd.command_type == "message":
                message_index += 1
                self.formatter.print_user_message(cmd.content, message_index)
                
                try:
                    if self.stream:
                        response = await self._run_streaming(agent_runner, cmd.content)
                    else:
                        response = await self._run_simple(agent_runner, cmd.content)
                    
                    self.last_response = response
                    
                except Exception as e:
                    self.formatter.print_error(str(e))
                    if self.verbosity >= 3:
                        import traceback
                        traceback.print_exc()
        
        success = self.failed_expects == 0
        self.formatter.print_footer(success, self.failed_expects)
        return success
    
    async def _create_default_runner(self) -> Callable[[str], str] | None:
        """Create a default agent runner from the project's graph.
        
        This implements the LangGraph interrupt/resume pattern:
        1. First call: Start graph with empty input, get initial interrupt prompt
        2. Subsequent calls: Resume with Command(resume=user_message)
        
        Returns:
            Async function that takes a message and returns response
        """
        try:
            # Try to dynamically import the project's graph
            # This assumes a standard LangGraph project structure
            import importlib
            from langgraph.checkpoint.memory import MemorySaver
            from langgraph.types import Command
            
            graph_module = self.config.graph_module
            module = importlib.import_module(graph_module)
            
            # Look for common graph variable names
            graph = None
            for name in ["graph", "pd_graph", "app", "workflow", "agent"]:
                if hasattr(module, name):
                    graph = getattr(module, name)
                    break
            
            # If no compiled graph found, try build_graph()
            if graph is None and hasattr(module, "build_graph"):
                builder = module.build_graph()
                # Compile with memory checkpointer for session persistence
                checkpointer = MemorySaver()
                graph = builder.compile(checkpointer=checkpointer)
            
            if graph is None:
                return None
            
            # Create a runner that handles interrupt/resume pattern
            # Following LangGraph docs: https://langchain-ai.github.io/langgraph/agents/human-in-the-loop
            thread_id = f"script_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Track whether graph has been initialized
            graph_initialized = [False]  # Use list to allow mutation in closure
            initial_prompt = [None]  # Store initial prompt from first run
            
            async def _run_graph(input_value) -> tuple[dict | None, str | None]:
                """Run graph and extract interrupt prompt if present."""
                config = {"configurable": {"thread_id": thread_id}}
                
                # Stream graph execution to get final state
                result = None
                async for event in graph.astream(input_value, config, stream_mode="values"):
                    result = event
                
                # Check for interrupt and extract prompt
                state = await graph.aget_state(config)
                interrupt_prompt = None
                
                if state.tasks:
                    for task in state.tasks:
                        if hasattr(task, 'interrupts') and task.interrupts:
                            for interrupt_obj in task.interrupts:
                                prompt = interrupt_obj.value.get("prompt", "")
                                if prompt:
                                    interrupt_prompt = prompt
                                    break
                        if interrupt_prompt:
                            break
                
                return result, interrupt_prompt
            
            async def runner(message: str) -> str:
                """Handle user message using interrupt/resume pattern.
                
                LangGraph Pattern:
                - Graph uses interrupt() to pause and request user input
                - Caller resumes with Command(resume=user_response)
                - First invocation starts fresh (empty input)
                - Subsequent invocations resume from interrupt
                """
                nonlocal graph_initialized, initial_prompt
                
                if not graph_initialized[0]:
                    # FIRST CALL: Initialize graph and get initial prompt
                    # Start graph with empty input - it will hit interrupt at user_input node
                    graph_initialized[0] = True
                    
                    if self.verbosity >= 2:
                        print(f"{Colors.DIM}Initializing graph (first run)...{Colors.RESET}")
                    
                    result, interrupt_prompt = await _run_graph({})
                    
                    if interrupt_prompt:
                        # Store initial prompt - we'll return it after resuming with first message
                        initial_prompt[0] = interrupt_prompt
                        
                        if self.verbosity >= 2:
                            print(f"{Colors.DIM}Got initial prompt, resuming with user message...{Colors.RESET}")
                        
                        # Now resume with the first user message
                        result, next_prompt = await _run_graph(Command(resume=message))
                        
                        if next_prompt:
                            return next_prompt
                        
                        # Fallback: extract from result
                        return self._extract_response(result)
                    else:
                        # No interrupt on first run - unusual but handle it
                        return self._extract_response(result)
                else:
                    # SUBSEQUENT CALLS: Resume from interrupt with user message
                    if self.verbosity >= 2:
                        print(f"{Colors.DIM}Resuming with Command(resume=...)...{Colors.RESET}")
                    
                    result, interrupt_prompt = await _run_graph(Command(resume=message))
                    
                    if interrupt_prompt:
                        return interrupt_prompt
                    
                    # No more interrupts - conversation may be ending
                    return self._extract_response(result)
            
            return runner
            
        except Exception as e:
            if self.verbosity >= 2:
                print(f"{Colors.DIM}Could not auto-create runner: {e}{Colors.RESET}")
                import traceback
                traceback.print_exc()
            return None
    
    def _extract_response(self, result: dict | None) -> str:
        """Extract a response string from graph result.
        
        Args:
            result: Graph result dict
            
        Returns:
            Extracted response string
        """
        if not result:
            return "No response"
        
        # Try next_prompt first (PD3r pattern)
        if "next_prompt" in result and result["next_prompt"]:
            return result["next_prompt"]
        
        # Try messages
        if "messages" in result and result["messages"]:
            last_msg = result["messages"][-1]
            if hasattr(last_msg, "content"):
                return last_msg.content
            return str(last_msg)
        
        return str(result)
    
    async def _run_simple(self, runner: Callable, message: str) -> str:
        """Run agent with simple (non-streaming) output."""
        if asyncio.iscoroutinefunction(runner):
            response = await runner(message)
        else:
            response = runner(message)
        
        self.formatter.print_agent_response(str(response))
        return str(response)
    
    async def _run_streaming(self, runner: Callable, message: str) -> str:
        """Run agent with streaming output."""
        self.formatter.print_streaming_start()
        
        # For now, fall back to non-streaming since we don't know the runner's capabilities
        if asyncio.iscoroutinefunction(runner):
            response = await runner(message)
        else:
            response = runner(message)
        
        response_str = str(response)
        
        # Simulate streaming for better UX
        for char in response_str:
            self.formatter.print_streaming_chunk(char)
            await asyncio.sleep(0.005)  # Small delay for effect
        
        self.formatter.print_streaming_end()
        return response_str


# =============================================================================
# Script Templates
# =============================================================================

SCRIPT_TEMPLATE = """# Agentscript Test File
# Created: {date}
#
# This script tests basic agent conversation flow.
# Lines starting with # are comments.
# Special commands:
#   @PAUSE - Wait for Enter key
#   @WAIT:<seconds> - Wait for specified seconds
#   @EXPECT:<text> - Assert response contains text
#   @END - End the conversation

# Start the conversation
Hello, I'd like to test the agent.

# Expect a greeting or acknowledgment
@EXPECT:hello

# Follow-up message
What can you help me with?

# Add a pause to review output
@PAUSE

# End the conversation
Thanks, goodbye!

@END
"""


def create_script_template(name: str, scripts_dir: Path) -> Path:
    """Create a new script template.
    
    Args:
        name: Name for the script
        scripts_dir: Directory to create script in
        
    Returns:
        Path to created script
    """
    scripts_dir.mkdir(parents=True, exist_ok=True)
    
    # Add .txt extension if not present
    if not name.endswith(".txt"):
        name += ".txt"
    
    script_path = scripts_dir / name
    
    content = SCRIPT_TEMPLATE.format(date=datetime.now().strftime("%Y-%m-%d"))
    script_path.write_text(content)
    
    return script_path


def list_scripts(scripts_dir: Path) -> list[Path]:
    """List available scripts.
    
    Args:
        scripts_dir: Directory containing scripts
        
    Returns:
        List of script paths
    """
    if not scripts_dir.exists():
        return []
    
    return sorted(scripts_dir.glob("*.txt"))


# =============================================================================
# Public API
# =============================================================================

def run_script(
    script_path: str | Path,
    stream: bool = False,
    verbosity: int = 1,
    agent_runner: Callable[[str], str] | None = None,
    config: ToolkitConfig | None = None,
) -> bool:
    """Run a conversation script (sync wrapper).
    
    Args:
        script_path: Path to script file
        stream: Stream responses in real-time
        verbosity: Output verbosity (0-3)
        agent_runner: Custom agent runner function
        config: Toolkit configuration
        
    Returns:
        True if successful, False otherwise
    """
    runner = ScriptRunner(config, stream, verbosity)
    return asyncio.run(runner.run_script(Path(script_path), agent_runner))


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="agentscript - Automated Agent Conversation Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Script Format:
  Each line is a user message sent to the agent.
  Lines starting with # are comments.
  
Special Commands:
  @PAUSE           - Wait for Enter key
  @WAIT:<seconds>  - Wait for specified seconds  
  @EXPECT:<text>   - Assert response contains text
  @END             - End the conversation

Examples:
  agentscript scripts/test.txt --stream -v 2
  agentscript --create my_test
  agentscript --list
        """,
    )
    
    parser.add_argument(
        "script",
        nargs="?",
        help="Path to script file",
    )
    parser.add_argument(
        "-s", "--stream",
        action="store_true",
        help="Stream responses in real-time",
    )
    parser.add_argument(
        "-v", "--verbosity",
        type=int,
        default=1,
        choices=[0, 1, 2, 3],
        help="Verbosity level (0=quiet, 1=normal, 2=verbose, 3=debug)",
    )
    parser.add_argument(
        "--create",
        metavar="NAME",
        help="Create a new script template",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available scripts",
    )
    parser.add_argument(
        "--scripts-dir",
        default="agent_toolkit/scripts",
        help="Directory for scripts (default: agent_toolkit/scripts)",
    )
    parser.add_argument(
        "--config",
        help="Path to config file",
    )
    parser.add_argument(
        "--project-root",
        help="Project root directory",
    )
    
    args = parser.parse_args()
    
    # Setup config
    if args.config:
        config = ToolkitConfig.from_file(args.config)
    else:
        config = ToolkitConfig.from_env()
    
    if args.project_root:
        config.project_root = Path(args.project_root)
    
    set_config(config)
    
    scripts_dir = config.project_root / args.scripts_dir
    
    # Handle commands
    if args.create:
        path = create_script_template(args.create, scripts_dir)
        print(f"Created script template: {path}")
        return
    
    if args.list:
        scripts = list_scripts(scripts_dir)
        if not scripts:
            print(f"No scripts found in {scripts_dir}")
            print(f"\nCreate one with: agentscript --create <name>")
        else:
            print("Available scripts:")
            for script in scripts:
                print(f"  {script.name}")
        return
    
    if not args.script:
        parser.print_help()
        return
    
    # Run script
    script_path = Path(args.script)
    if not script_path.is_absolute():
        # Try relative to scripts dir first
        if (scripts_dir / script_path).exists():
            script_path = scripts_dir / script_path
        elif not script_path.exists():
            # Try with .txt extension
            if (scripts_dir / f"{script_path}.txt").exists():
                script_path = scripts_dir / f"{script_path}.txt"
    
    success = run_script(
        script_path,
        stream=args.stream,
        verbosity=args.verbosity,
        config=config,
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
