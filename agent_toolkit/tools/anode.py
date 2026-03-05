#!/usr/bin/env python3
"""anode - LangGraph Node Analysis Tool.

Analyzes individual node performance from trace logs using LLM-powered insights.

Usage:
    anode <node_name> [-n N]     Analyze a specific node from last N runs
    anode full [-n N]           Analyze the complete graph
    anode --list                 List available nodes
    anode --costs [-n N]        Show cost breakdown

Examples:
    anode init_node -n 5        Analyze init_node from last 5 runs
    anode full -n 3             Full graph analysis from 3 runs
    anode evaluate_fes_factors_node --verbose
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add parent to path for imports when run directly
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent_toolkit.core.config import ToolkitConfig, get_config, set_config
from agent_toolkit.core.trace_analyzer import TraceAnalyzer
from agent_toolkit.core.node_analyzer import NodeAnalyzer
from agent_toolkit.prompts import (
    NODE_ANALYSIS_SYSTEM,
    NODE_ANALYSIS_USER,
    GRAPH_ANALYSIS_SYSTEM,
    GRAPH_ANALYSIS_USER,
)


class AnodeAnalyzer:
    """Main analyzer for the anode tool."""
    
    def __init__(self, config: ToolkitConfig | None = None):
        """Initialize analyzer.
        
        Args:
            config: Toolkit configuration, or use global config if None
        """
        self.config = config or get_config()
        self.trace_analyzer = TraceAnalyzer(self.config.get_trace_path())
        self.node_analyzer = NodeAnalyzer(
            self.config.get_nodes_path(),
            self.config.get_trace_path()
        )
    
    async def analyze_node(
        self,
        node_name: str,
        n_runs: int = 5,
        verbose: bool = False,
        output_file: str | None = None,
        skip_llm: bool = False,
    ) -> str:
        """Analyze a specific node.
        
        Args:
            node_name: Name of the node to analyze
            n_runs: Number of recent runs to analyze
            verbose: Print verbose output
            output_file: Optional file to save analysis
            skip_llm: Skip LLM analysis and show raw metrics
            
        Returns:
            Analysis report as string
        """
        if verbose:
            print(f"🔍 Analyzing node: {node_name}")
            print(f"   Loading last {n_runs} runs...")
        
        # Get node executions across runs
        executions = self.trace_analyzer.get_node_executions_across_runs(
            node_name, n_runs
        )
        
        if not executions:
            return f"❌ No executions found for node '{node_name}' in the last {n_runs} runs."
        
        if verbose:
            total_execs = sum(len(e) for _, e in executions)
            print(f"   Found {total_execs} executions across {len(executions)} runs")
        
        # Get source info
        source_info = self.node_analyzer.get_source_info(node_name)
        if verbose and source_info:
            print(f"   Source file: {source_info.file_path}")
        
        # Calculate metrics
        metrics = self.node_analyzer.analyze_executions(executions)
        
        if verbose:
            print(f"   Success rate: {metrics.get('success_rate', 0):.1%}")
            print(f"   Avg cost: ${metrics.get('avg_cost_per_exec', 0):.6f}")
            print(f"   Preparing LLM analysis...")
        
        # Prepare context for LLM
        context = self.node_analyzer.prepare_analysis_context(
            node_name, source_info, executions, metrics
        )
        
        # Skip LLM if requested
        if skip_llm:
            report = f"# Raw Analysis: {node_name}\n\n{context}"
        else:
            # Run LLM analysis
            report = await self._run_llm_analysis(
                NODE_ANALYSIS_SYSTEM,
                NODE_ANALYSIS_USER.format(
                    context=context,
                    avg_cost=f"{metrics.get('avg_cost_per_exec', 0):.6f}"
                ),
                verbose=verbose,
            )
        
        # Save if requested
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(report)
            if verbose:
                print(f"   Saved to: {output_path}")
        
        return report
    
    async def analyze_full_graph(
        self,
        n_runs: int = 3,
        verbose: bool = False,
        output_file: str | None = None,
        skip_llm: bool = False,
    ) -> str:
        """Analyze the complete graph.
        
        Args:
            n_runs: Number of recent runs to analyze
            verbose: Print verbose output
            output_file: Optional file to save analysis
            skip_llm: Skip LLM analysis and show raw metrics
            
        Returns:
            Analysis report as string
        """
        if verbose:
            print("🔍 Analyzing full graph...")
            print(f"   Loading last {n_runs} runs...")
        
        # Load README
        readme_path = self.config.get_readme_path()
        readme = ""
        if readme_path.exists():
            readme = readme_path.read_text()
            if len(readme) > 5000:
                readme = readme[:5000] + "\n\n[... truncated ...]"
        
        # Load Architecture Decision Records
        adrs = self._load_architecture_decisions()
        if verbose and adrs:
            print(f"   Loaded ADRs from docs/decisions/")
        
        # Load graph structure (try to find and parse main_graph.py)
        graph_structure = self._extract_graph_structure()
        
        # Get node summary
        node_names = self.node_analyzer.get_all_node_names()
        node_summary = self._build_node_summary(node_names, n_runs)
        
        # Get run statistics
        cost_summary = self.trace_analyzer.get_cost_summary(n_runs)
        run_stats = self._format_run_stats(cost_summary)
        
        # Get flow examples
        flow_examples = self._get_flow_examples(n_runs)
        
        if verbose:
            print(f"   Found {len(node_names)} nodes")
            print(f"   Graph structure extracted")
            if not skip_llm:
                print(f"   Preparing LLM analysis...")
        
        # Skip LLM if requested
        if skip_llm:
            report = self._format_raw_graph_report(
                graph_structure, node_names, node_summary, run_stats, flow_examples
            )
        else:
            # Run LLM analysis
            report = await self._run_llm_analysis(
                GRAPH_ANALYSIS_SYSTEM,
                GRAPH_ANALYSIS_USER.format(
                    readme=readme,
                    adrs=adrs,
                    graph_structure=graph_structure,
                    node_summary=node_summary,
                    run_stats=run_stats,
                    flow_examples=flow_examples,
                ),
                verbose=verbose,
            )
        
        # Save if requested
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(report)
            if verbose:
                print(f"   Saved to: {output_path}")
        
        return report
    
    def _format_raw_graph_report(
        self,
        graph_structure: str,
        node_names: list[str],
        node_summary: str,
        run_stats: str,
        flow_examples: str,
    ) -> str:
        """Format raw graph report without LLM analysis."""
        sections = [
            "# PD3r Graph Analysis Report (Raw Metrics)",
            "",
            "## Graph Overview",
            f"- **Total Nodes:** {len(node_names)}",
            "",
            "## Graph Structure",
            graph_structure if graph_structure else "_No graph structure found_",
            "",
            "## Node Inventory",
            node_summary if node_summary else "_No node data available_",
            "",
            "## Run Statistics",
            run_stats if run_stats else "_No trace data available_",
            "",
            "## Flow Examples",
            flow_examples if flow_examples else "_No flow examples available_",
        ]
        return "\n".join(sections)
    
    async def _run_llm_analysis(
        self,
        system_prompt: str,
        user_prompt: str,
        verbose: bool = False,
    ) -> str:
        """Run LLM analysis with the configured model.
        
        Uses GPT-5.2 via OpenAI API (project standard for analysis).
        
        Args:
            system_prompt: System prompt
            user_prompt: User prompt with context
            verbose: Print verbose output
            
        Returns:
            LLM response
        """
        try:
            # Try to use langchain-openai (preferred)
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import HumanMessage, SystemMessage
            
            if verbose:
                print(f"   Using model: {self.config.analysis_model}")
            
            llm = ChatOpenAI(
                model=self.config.analysis_model,
                temperature=self.config.analysis_temperature,
            )
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
            
            response = await llm.ainvoke(messages)
            return response.content
            
        except ImportError:
            # Fallback to httpx direct call
            return await self._direct_openai_call(system_prompt, user_prompt, verbose)
        except Exception as e:
            return f"❌ LLM Analysis Error: {e}\n\nRaw context was prepared but analysis failed."
    
    async def _direct_openai_call(
        self,
        system_prompt: str,
        user_prompt: str,
        verbose: bool = False,
    ) -> str:
        """Direct OpenAI API call as fallback."""
        import httpx
        
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return "❌ Error: OPENAI_API_KEY not set. Cannot run LLM analysis."
        
        if verbose:
            print(f"   Using direct API call to {self.config.analysis_model}")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.config.analysis_model,
                    "temperature": self.config.analysis_temperature,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
                timeout=120.0,
            )
            
            if response.status_code != 200:
                return f"❌ API Error: {response.status_code} - {response.text}"
            
            data = response.json()
            return data["choices"][0]["message"]["content"]
    
    def _load_architecture_decisions(self) -> str:
        """Load Architecture Decision Records (ADRs) from docs/decisions/.
        
        These are critical constraints that the analysis MUST respect.
        Filters to only include ADRs with 'no-mock', 'no-heuristic', 
        'llm-driven', or similar architectural constraint keywords.
        
        Returns:
            Formatted string of relevant ADRs
        """
        decisions_path = self.config.get_decisions_path()
        if not decisions_path.exists():
            return "(No ADR directory found)"
        
        # Keywords that indicate architectural constraints
        constraint_keywords = [
            "no-mock", "no-heuristic", "llm-driven", "forbidden", 
            "required", "must", "policy", "routing"
        ]
        
        adrs = []
        for adr_file in sorted(decisions_path.glob("*.md")):
            # Skip index files
            if adr_file.name.lower() in ("index.md", "readme.md", "idea-.md"):
                continue
            
            try:
                content = adr_file.read_text()
                # Check if this ADR contains architectural constraints
                content_lower = content.lower()
                if any(kw in content_lower for kw in constraint_keywords):
                    # Truncate very long ADRs but keep the important parts
                    if len(content) > 2000:
                        # Keep title and first 2000 chars
                        content = content[:2000] + "\n\n[... truncated ...]"
                    adrs.append(f"## {adr_file.stem}\n\n{content}")
            except Exception:
                continue
        
        if not adrs:
            return "(No architectural constraint ADRs found)"
        
        return "\n\n---\n\n".join(adrs)
    
    def _extract_graph_structure(self) -> str:
        """Extract graph structure from main_graph.py."""
        # Try to find graph file
        graph_module = self.config.graph_module
        parts = graph_module.split(".")
        
        # Try common paths
        possible_paths = [
            self.config.project_root / ("/".join(parts) + ".py"),
            self.config.project_root / "src" / "graphs" / "main_graph.py",
            self.config.project_root / "src" / "graph.py",
        ]
        
        for path in possible_paths:
            if path.exists():
                try:
                    content = path.read_text()
                    # Extract relevant sections
                    lines = []
                    in_build = False
                    for line in content.split("\n"):
                        if "def build_graph" in line or "StateGraph" in line:
                            in_build = True
                        if in_build:
                            lines.append(line)
                        if in_build and line.strip().startswith("return"):
                            break
                    if lines:
                        return "```python\n" + "\n".join(lines) + "\n```"
                except Exception:
                    pass
        
        # Try to find mermaid diagram
        mmd_path = self.config.project_root / "output" / "graphs" / "main_graph.mmd"
        if mmd_path.exists():
            try:
                return "```mermaid\n" + mmd_path.read_text() + "\n```"
            except Exception:
                pass
        
        return "(Graph structure not found)"
    
    def _build_node_summary(self, node_names: list[str], n_runs: int) -> str:
        """Build a summary of all nodes."""
        lines = []
        for name in node_names:
            source_info = self.node_analyzer.get_source_info(name)
            if source_info:
                desc = source_info.docstring.split("\n")[0] if source_info.docstring else "No description"
                llm_marker = "🤖" if source_info.has_llm_call else "  "
                lines.append(f"- {llm_marker} **{name}**: {desc}")
            else:
                lines.append(f"-    **{name}**: (source not found)")
        
        return "\n".join(lines)
    
    def _format_run_stats(self, cost_summary: dict[str, Any]) -> str:
        """Format run statistics."""
        if "error" in cost_summary:
            return cost_summary["error"]
        
        lines = [
            f"- **Runs Analyzed:** {cost_summary.get('runs_analyzed', 0)}",
            f"- **Total Cost:** ${cost_summary.get('total_cost', 0):.6f}",
            f"- **Avg Cost/Run:** ${cost_summary.get('avg_cost_per_run', 0):.6f}",
            f"- **Total Tokens:** {cost_summary.get('total_tokens', 0):,}",
            "",
            "**Cost by Node:**",
        ]
        
        for name, data in cost_summary.get("cost_by_node", {}).items():
            lines.append(f"  - {name}: ${data['total']:.6f} ({data['count']} calls)")
        
        return "\n".join(lines)
    
    def _get_flow_examples(self, n_runs: int) -> str:
        """Get example execution flows."""
        runs = self.trace_analyzer.load_recent_runs(min(n_runs, 2))
        if not runs:
            return "(No runs available)"
        
        lines = []
        for run in runs[:2]:
            lines.append(f"\n### Run {run.summary.run_id}")
            lines.append(f"Cost: ${run.summary.total_cost:.6f}, Nodes: {len(run.node_executions)}")
            lines.append("Flow:")
            for node in run.node_executions[:15]:  # Limit to 15 nodes
                status = "✓" if node.success else "✗"
                lines.append(f"  {status} {node.node_name} ({node.duration_ms:.0f}ms)")
            if len(run.node_executions) > 15:
                lines.append(f"  ... and {len(run.node_executions) - 15} more nodes")
        
        return "\n".join(lines)
    
    def list_nodes(self) -> str:
        """List all available nodes."""
        names = self.node_analyzer.get_all_node_names()
        
        if not names:
            return "No nodes found in nodes directory."
        
        lines = ["Available nodes:", ""]
        for name in names:
            source_info = self.node_analyzer.get_source_info(name)
            if source_info and source_info.docstring:
                desc = source_info.docstring.split("\n")[0][:60]
                lines.append(f"  {name}")
                lines.append(f"    └─ {desc}")
            else:
                lines.append(f"  {name}")
        
        return "\n".join(lines)
    
    def show_costs(self, n_runs: int = 10) -> str:
        """Show cost breakdown."""
        return self.trace_analyzer.format_cost_report(n_runs)


def analyze_node(
    node_name: str,
    n_runs: int = 5,
    verbose: bool = False,
    config: ToolkitConfig | None = None,
) -> str:
    """Analyze a node (sync wrapper).
    
    Args:
        node_name: Node name or 'full' for complete graph
        n_runs: Number of runs to analyze
        verbose: Print verbose output
        config: Optional config
        
    Returns:
        Analysis report
    """
    analyzer = AnodeAnalyzer(config)
    
    if node_name == "full":
        return asyncio.run(analyzer.analyze_full_graph(n_runs, verbose))
    else:
        return asyncio.run(analyzer.analyze_node(node_name, n_runs, verbose))


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="anode - LangGraph Node Analysis Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  anode init_node -n 5        Analyze init_node from last 5 runs
  anode full -n 3             Full graph analysis from 3 runs
  anode --list                List all available nodes
  anode --costs               Show cost breakdown
        """,
    )
    
    parser.add_argument(
        "node_name",
        nargs="?",
        help="Node name to analyze, or 'full' for complete graph",
    )
    parser.add_argument(
        "-n", "--runs",
        type=int,
        default=5,
        help="Number of recent runs to analyze (default: 5)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "-o", "--output",
        help="Save analysis to file",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available nodes",
    )
    parser.add_argument(
        "--costs",
        action="store_true",
        help="Show cost breakdown",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Show raw metrics without LLM analysis",
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
    analyzer = AnodeAnalyzer(config)
    
    # Handle commands
    if args.list:
        print(analyzer.list_nodes())
        return
    
    if args.costs:
        print(analyzer.show_costs(args.runs))
        return
    
    if not args.node_name:
        parser.print_help()
        return
    
    # Auto-generate output file if not specified
    output_file = args.output
    if not output_file:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = config.project_root / "output" / "analysis"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = str(output_dir / f"anode_{args.node_name}_{timestamp}.md")
    
    # Run analysis
    print(f"\n{'=' * 60}")
    print(f"  ANODE - LangGraph Node Analyzer")
    print(f"{'=' * 60}\n")
    
    if args.node_name == "full":
        report = asyncio.run(analyzer.analyze_full_graph(
            args.runs, args.verbose, output_file, skip_llm=args.raw
        ))
    else:
        report = asyncio.run(analyzer.analyze_node(
            args.node_name, args.runs, args.verbose, output_file, skip_llm=args.raw
        ))
    
    print(report)
    
    print(f"\n📄 Analysis saved to: {output_file}")


if __name__ == "__main__":
    main()
