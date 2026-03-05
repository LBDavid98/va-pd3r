"""Trace analyzer for loading and processing trace logs.

This module handles loading JSONL trace files and provides methods for
filtering, aggregating, and preparing trace data for analysis.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class LLMCallData:
    """Structured data for a single LLM call."""
    
    call_id: str
    model: str
    temperature: float
    prompt: str
    response: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_estimate: float
    duration_ms: float
    success: bool
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class NodeExecutionData:
    """Structured data for a single node execution."""
    
    trace_id: str
    timestamp: str
    node_name: str
    state_on_entry: dict[str, Any]
    state_on_exit: dict[str, Any] | None
    llm_calls: list[LLMCallData]
    duration_ms: float
    success: bool
    error: str | None = None
    
    @property
    def total_llm_cost(self) -> float:
        """Total cost of all LLM calls in this node."""
        return sum(call.cost_estimate for call in self.llm_calls)
    
    @property
    def total_llm_tokens(self) -> int:
        """Total tokens used by all LLM calls."""
        return sum(call.total_tokens for call in self.llm_calls)


@dataclass
class RunSummary:
    """Summary data for a complete run."""
    
    run_id: str
    start_time: str | None
    total_cost: float
    total_tokens: int
    num_nodes: int
    num_llm_calls: int
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunSummary":
        return cls(
            run_id=data.get("run_id", "unknown"),
            start_time=data.get("start_time"),
            total_cost=data.get("total_cost", 0.0),
            total_tokens=data.get("total_tokens", 0),
            num_nodes=data.get("num_nodes", 0),
            num_llm_calls=data.get("num_llm_calls", 0),
        )


@dataclass
class TraceRun:
    """Complete data for a single agent run."""
    
    file_path: Path
    summary: RunSummary
    node_executions: list[NodeExecutionData]
    
    @property
    def nodes_by_name(self) -> dict[str, list[NodeExecutionData]]:
        """Group node executions by node name."""
        result: dict[str, list[NodeExecutionData]] = {}
        for node in self.node_executions:
            if node.node_name not in result:
                result[node.node_name] = []
            result[node.node_name].append(node)
        return result
    
    def get_node_executions(self, node_name: str) -> list[NodeExecutionData]:
        """Get all executions of a specific node."""
        return [n for n in self.node_executions if n.node_name == node_name]


class TraceAnalyzer:
    """Analyzer for loading and processing trace logs.
    
    Example:
        analyzer = TraceAnalyzer("output/logs")
        runs = analyzer.load_recent_runs(5)
        
        for run in runs:
            print(f"Run {run.summary.run_id}: ${run.summary.total_cost:.4f}")
    """
    
    def __init__(self, trace_dir: str | Path):
        """Initialize trace analyzer.
        
        Args:
            trace_dir: Directory containing trace JSONL files
        """
        self.trace_dir = Path(trace_dir)
    
    def list_trace_files(self, max_age_days: int | None = None) -> list[Path]:
        """List all trace files, sorted by modification time (newest first).
        
        Args:
            max_age_days: Only include files modified within this many days
            
        Returns:
            List of trace file paths
        """
        if not self.trace_dir.exists():
            return []
        
        files = []
        cutoff = None
        if max_age_days:
            cutoff = datetime.now().timestamp() - (max_age_days * 24 * 3600)
        
        for f in self.trace_dir.glob("*.jsonl"):
            if cutoff and f.stat().st_mtime < cutoff:
                continue
            files.append(f)
        
        # Sort by modification time, newest first
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        return files
    
    def load_trace(self, file_path: Path) -> TraceRun | None:
        """Load a single trace file.
        
        Args:
            file_path: Path to the JSONL trace file
            
        Returns:
            TraceRun object or None if file couldn't be loaded
        """
        if not file_path.exists():
            return None
        
        try:
            with open(file_path) as f:
                lines = f.readlines()
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return None
        
        if not lines:
            return None
        
        # First line should be run summary
        try:
            first = json.loads(lines[0])
            if first.get("event") == "run_summary":
                summary = RunSummary.from_dict(first)
                start_idx = 1
            else:
                # No summary, create a default one
                summary = RunSummary(
                    run_id="unknown",
                    start_time=None,
                    total_cost=0.0,
                    total_tokens=0,
                    num_nodes=0,
                    num_llm_calls=0,
                )
                start_idx = 0
        except json.JSONDecodeError:
            return None
        
        # Parse node executions
        node_executions = []
        for line in lines[start_idx:]:
            try:
                data = json.loads(line)
                if data.get("event") != "node_execution":
                    continue
                
                # Parse LLM calls
                llm_calls = []
                for call_data in data.get("llm_calls", []):
                    llm_calls.append(LLMCallData(
                        call_id=call_data.get("call_id", ""),
                        model=call_data.get("model", "unknown"),
                        temperature=call_data.get("temperature", 0.0),
                        prompt=call_data.get("prompt", ""),
                        response=call_data.get("response", ""),
                        input_tokens=call_data.get("input_tokens", 0),
                        output_tokens=call_data.get("output_tokens", 0),
                        total_tokens=call_data.get("input_tokens", 0) + call_data.get("output_tokens", 0),
                        cost_estimate=call_data.get("cost_estimate", 0.0),
                        duration_ms=call_data.get("duration_ms", 0.0),
                        success=call_data.get("success", True),
                        error=call_data.get("error"),
                    ))
                
                node_executions.append(NodeExecutionData(
                    trace_id=data.get("trace_id", ""),
                    timestamp=data.get("timestamp", ""),
                    node_name=data.get("node_name", "unknown"),
                    state_on_entry=data.get("state_on_entry", {}),
                    state_on_exit=data.get("state_on_exit"),
                    llm_calls=llm_calls,
                    duration_ms=data.get("duration_ms", 0.0),
                    success=data.get("success", True),
                    error=data.get("error"),
                ))
            except json.JSONDecodeError:
                continue
        
        return TraceRun(
            file_path=file_path,
            summary=summary,
            node_executions=node_executions,
        )
    
    def load_recent_runs(self, n: int = 5, max_age_days: int | None = None) -> list[TraceRun]:
        """Load the N most recent trace runs.
        
        Args:
            n: Number of runs to load
            max_age_days: Only include runs from within this many days
            
        Returns:
            List of TraceRun objects, newest first
        """
        files = self.list_trace_files(max_age_days)[:n]
        runs = []
        for f in files:
            run = self.load_trace(f)
            if run:
                runs.append(run)
        return runs
    
    def get_node_executions_across_runs(
        self, 
        node_name: str, 
        n_runs: int = 5
    ) -> list[tuple[TraceRun, list[NodeExecutionData]]]:
        """Get all executions of a specific node across recent runs.
        
        Args:
            node_name: Name of the node to find
            n_runs: Number of recent runs to search
            
        Returns:
            List of (TraceRun, list[NodeExecutionData]) tuples
        """
        runs = self.load_recent_runs(n_runs)
        results = []
        for run in runs:
            executions = run.get_node_executions(node_name)
            if executions:
                results.append((run, executions))
        return results
    
    def get_all_node_names(self, n_runs: int = 10) -> set[str]:
        """Get all unique node names across recent runs.
        
        Args:
            n_runs: Number of runs to search
            
        Returns:
            Set of node names
        """
        runs = self.load_recent_runs(n_runs)
        names: set[str] = set()
        for run in runs:
            for node in run.node_executions:
                names.add(node.node_name)
        return names
    
    def get_cost_summary(self, n_runs: int = 10) -> dict[str, Any]:
        """Get cost summary across recent runs.
        
        Args:
            n_runs: Number of runs to analyze
            
        Returns:
            Dictionary with cost statistics
        """
        runs = self.load_recent_runs(n_runs)
        if not runs:
            return {"error": "No traces found"}
        
        costs = [r.summary.total_cost for r in runs]
        tokens = [r.summary.total_tokens for r in runs]
        
        # Cost by node
        node_costs: dict[str, list[float]] = {}
        for run in runs:
            for node in run.node_executions:
                if node.node_name not in node_costs:
                    node_costs[node.node_name] = []
                node_costs[node.node_name].append(node.total_llm_cost)
        
        return {
            "runs_analyzed": len(runs),
            "total_cost": sum(costs),
            "avg_cost_per_run": sum(costs) / len(costs) if costs else 0,
            "min_cost": min(costs) if costs else 0,
            "max_cost": max(costs) if costs else 0,
            "total_tokens": sum(tokens),
            "avg_tokens_per_run": sum(tokens) / len(tokens) if tokens else 0,
            "cost_by_node": {
                name: {
                    "total": sum(c),
                    "avg": sum(c) / len(c) if c else 0,
                    "count": len(c),
                }
                for name, c in node_costs.items()
            },
        }
    
    def format_cost_report(self, n_runs: int = 10) -> str:
        """Generate a formatted cost report.
        
        Args:
            n_runs: Number of runs to analyze
            
        Returns:
            Formatted string report
        """
        summary = self.get_cost_summary(n_runs)
        
        if "error" in summary:
            return f"Error: {summary['error']}"
        
        lines = [
            "=" * 60,
            "COST ANALYSIS REPORT",
            "=" * 60,
            f"Runs Analyzed: {summary['runs_analyzed']}",
            "",
            "Overall Costs:",
            f"  Total:   ${summary['total_cost']:.6f}",
            f"  Average: ${summary['avg_cost_per_run']:.6f} per run",
            f"  Range:   ${summary['min_cost']:.6f} - ${summary['max_cost']:.6f}",
            "",
            "Token Usage:",
            f"  Total:   {summary['total_tokens']:,}",
            f"  Average: {summary['avg_tokens_per_run']:,.0f} per run",
            "",
            "Cost by Node:",
        ]
        
        # Sort nodes by total cost
        nodes = sorted(
            summary["cost_by_node"].items(),
            key=lambda x: x[1]["total"],
            reverse=True
        )
        
        for name, data in nodes:
            lines.append(f"  {name}:")
            lines.append(f"    Total: ${data['total']:.6f} ({data['count']} calls)")
            lines.append(f"    Avg:   ${data['avg']:.6f}")
        
        lines.append("=" * 60)
        return "\n".join(lines)
