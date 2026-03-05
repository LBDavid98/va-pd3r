"""LangGraph Agent Toolkit - Performance Tuning & Analysis Tools.

A portable toolkit for analyzing, testing, and tuning LangGraph agents.
Import this toolkit to any LangGraph project for comprehensive agent analysis.

Quick Start:
    from agent_toolkit import anode, agentscript
    
    # Analyze a specific node from last 5 runs
    anode("init_node", n=5)
    
    # Run a scripted conversation
    agentscript("scripts/test_flow.txt", stream=True)

CLI Usage:
    anode <node_name> -N <num_traces>
    agentscript <script_path> --stream --verbose
    agent_health                           # Run health diagnostics
    agent_lint                             # Check for common issues

See README.md for full documentation.
"""

__version__ = "0.1.0"

from .core.trace_analyzer import TraceAnalyzer
from .core.node_analyzer import NodeAnalyzer
from .tools.anode import analyze_node, main as anode_main
from .tools.agentscript import run_script, main as agentscript_main
from .tools.health_check import run_health_check
from .tools.lint import lint_graph

__all__ = [
    "TraceAnalyzer",
    "NodeAnalyzer",
    "analyze_node",
    "run_script",
    "run_health_check",
    "lint_graph",
    "anode_main",
    "agentscript_main",
]
