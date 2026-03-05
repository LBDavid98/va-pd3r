"""Node analyzer for deep analysis of individual node behavior.

This module provides tools for analyzing node source code, traces, and
generating improvement recommendations via LLM analysis.
"""

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .trace_analyzer import TraceRun, NodeExecutionData, LLMCallData
from .config import get_config


@dataclass
class NodeSourceInfo:
    """Information extracted from node source code."""
    
    name: str
    file_path: Path
    source_code: str
    docstring: str | None
    function_signature: str
    imports: list[str]
    dependencies: list[str]  # Other modules this node uses
    has_llm_call: bool
    uses_prompts: bool
    prompt_references: list[str]  # Prompt file references
    state_fields_read: list[str]  # State fields accessed
    state_fields_written: list[str]  # State fields modified
    
    @classmethod
    def from_file(cls, file_path: Path, node_name: str) -> "NodeSourceInfo | None":
        """Extract node info from source file.
        
        Args:
            file_path: Path to the node file
            node_name: Name of the node function
            
        Returns:
            NodeSourceInfo or None if not found
        """
        if not file_path.exists():
            return None
        
        try:
            source = file_path.read_text()
        except Exception:
            return None
        
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return None
        
        # Find the node function
        node_func = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == node_name:
                node_func = node
                break
            if isinstance(node, ast.AsyncFunctionDef) and node.name == node_name:
                node_func = node
                break
        
        if not node_func:
            return None
        
        # Extract imports
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append(f"{module}.{alias.name}")
        
        # Extract docstring
        docstring = ast.get_docstring(node_func)
        
        # Get function signature
        args = []
        for arg in node_func.args.args:
            args.append(arg.arg)
        sig = f"def {node_func.name}({', '.join(args)})"
        
        # Find state field access patterns
        state_reads = set()
        state_writes = set()
        
        # Look for state.get("field") or state["field"] patterns
        get_pattern = re.compile(r'state\.get\(["\'](\w+)["\']')
        bracket_pattern = re.compile(r'state\[["\'](\w+)["\']')
        
        for match in get_pattern.finditer(source):
            state_reads.add(match.group(1))
        for match in bracket_pattern.finditer(source):
            state_reads.add(match.group(1))
        
        # Check for LLM usage
        has_llm = any(x in source for x in [
            "traced_llm_call", "ChatOpenAI", "llm.invoke", 
            "llm.ainvoke", "with_structured_output"
        ])
        
        # Check for prompt usage
        uses_prompts = "prompts" in source.lower() or "template" in source.lower()
        prompt_refs = re.findall(r'from\s+\w+\.prompts\.(\w+)\s+import', source)
        
        # Find dependencies
        deps = [
            imp.split(".")[0] for imp in imports 
            if imp.startswith("src.") or imp.startswith(".")
        ]
        
        return cls(
            name=node_name,
            file_path=file_path,
            source_code=source,
            docstring=docstring,
            function_signature=sig,
            imports=imports,
            dependencies=list(set(deps)),
            has_llm_call=has_llm,
            uses_prompts=uses_prompts,
            prompt_references=prompt_refs,
            state_fields_read=list(state_reads),
            state_fields_written=[],  # Would need more sophisticated analysis
        )


@dataclass
class NodeAnalysisResult:
    """Results of analyzing a node's behavior."""
    
    node_name: str
    executions_analyzed: int
    success_rate: float
    avg_duration_ms: float
    avg_llm_cost: float
    avg_tokens: int
    
    # Source analysis
    source_info: NodeSourceInfo | None
    
    # Execution patterns
    common_entry_states: list[dict[str, Any]]
    common_errors: list[str]
    
    # LLM call analysis
    llm_calls_per_execution: float
    models_used: list[str]
    temperatures_used: list[float]
    avg_prompt_length: float
    avg_response_length: float
    
    # Recommendations (from LLM analysis)
    recommendations: list[str] = field(default_factory=list)
    analysis_report: str = ""


class NodeAnalyzer:
    """Analyzer for deep node behavior analysis.
    
    This class combines trace data with source code analysis to provide
    comprehensive insights into node behavior and improvement opportunities.
    
    Example:
        analyzer = NodeAnalyzer("src/nodes", "output/logs")
        result = analyzer.analyze("init_node", n_runs=5)
        print(result.analysis_report)
    """
    
    def __init__(self, nodes_dir: str | Path, trace_dir: str | Path):
        """Initialize node analyzer.
        
        Args:
            nodes_dir: Directory containing node source files
            trace_dir: Directory containing trace logs
        """
        self.nodes_dir = Path(nodes_dir)
        self.trace_dir = Path(trace_dir)
    
    def find_node_file(self, node_name: str) -> Path | None:
        """Find the source file for a node.
        
        Args:
            node_name: Name of the node function
            
        Returns:
            Path to the file or None if not found
        """
        # Common patterns: node_name.py, node_name_node.py, etc.
        patterns = [
            f"{node_name}.py",
            f"{node_name.replace('_node', '')}_node.py",
            f"{node_name}_node.py",
        ]
        
        for pattern in patterns:
            path = self.nodes_dir / pattern
            if path.exists():
                return path
        
        # Search all files for the function
        for f in self.nodes_dir.glob("*.py"):
            try:
                content = f.read_text()
                if f"def {node_name}(" in content or f"async def {node_name}(" in content:
                    return f
            except Exception:
                continue
        
        return None
    
    def get_source_info(self, node_name: str) -> NodeSourceInfo | None:
        """Get source code information for a node.
        
        Args:
            node_name: Name of the node function
            
        Returns:
            NodeSourceInfo or None if not found
        """
        file_path = self.find_node_file(node_name)
        if not file_path:
            return None
        
        return NodeSourceInfo.from_file(file_path, node_name)
    
    def analyze_executions(
        self, 
        executions: list[tuple[TraceRun, list[NodeExecutionData]]]
    ) -> dict[str, Any]:
        """Analyze a set of node executions.
        
        Args:
            executions: List of (run, executions) tuples
            
        Returns:
            Dictionary of analysis metrics
        """
        all_execs: list[NodeExecutionData] = []
        for run, execs in executions:
            all_execs.extend(execs)
        
        if not all_execs:
            return {"error": "No executions to analyze"}
        
        # Calculate metrics
        success_count = sum(1 for e in all_execs if e.success)
        total_duration = sum(e.duration_ms for e in all_execs)
        
        # LLM metrics
        all_llm_calls: list[LLMCallData] = []
        for exec in all_execs:
            all_llm_calls.extend(exec.llm_calls)
        
        models = set()
        temps = set()
        prompt_lengths = []
        response_lengths = []
        
        for call in all_llm_calls:
            models.add(call.model)
            temps.add(call.temperature)
            prompt_lengths.append(len(call.prompt))
            response_lengths.append(len(call.response))
        
        # Collect errors
        errors = [e.error for e in all_execs if e.error]
        
        # Collect common entry states (simplified keys)
        entry_keys: dict[str, int] = {}
        for exec in all_execs:
            for key in exec.state_on_entry.keys():
                entry_keys[key] = entry_keys.get(key, 0) + 1
        
        return {
            "total_executions": len(all_execs),
            "success_rate": success_count / len(all_execs),
            "avg_duration_ms": total_duration / len(all_execs),
            "total_llm_calls": len(all_llm_calls),
            "avg_llm_calls_per_exec": len(all_llm_calls) / len(all_execs) if all_execs else 0,
            "models_used": list(models),
            "temperatures_used": sorted(list(temps)),
            "avg_prompt_length": sum(prompt_lengths) / len(prompt_lengths) if prompt_lengths else 0,
            "avg_response_length": sum(response_lengths) / len(response_lengths) if response_lengths else 0,
            "total_cost": sum(c.cost_estimate for c in all_llm_calls),
            "avg_cost_per_exec": sum(c.cost_estimate for c in all_llm_calls) / len(all_execs) if all_execs else 0,
            "total_tokens": sum(c.total_tokens for c in all_llm_calls),
            "common_errors": list(set(errors))[:5],
            "state_keys_used": entry_keys,
        }
    
    def prepare_analysis_context(
        self,
        node_name: str,
        source_info: NodeSourceInfo | None,
        executions: list[tuple[TraceRun, list[NodeExecutionData]]],
        metrics: dict[str, Any],
    ) -> str:
        """Prepare context for LLM analysis.
        
        Args:
            node_name: Name of the node
            source_info: Source code info
            executions: Execution data
            metrics: Calculated metrics
            
        Returns:
            Formatted context string for LLM
        """
        sections = []
        
        # Header
        sections.append(f"# Node Analysis: {node_name}\n")
        
        # Source code section
        if source_info:
            sections.append("## Source Code\n")
            sections.append(f"**File:** {source_info.file_path}\n")
            if source_info.docstring:
                sections.append(f"**Docstring:**\n```\n{source_info.docstring}\n```\n")
            sections.append(f"**Signature:** `{source_info.function_signature}`\n")
            sections.append(f"**Has LLM Call:** {source_info.has_llm_call}\n")
            sections.append(f"**Uses Prompts:** {source_info.uses_prompts}\n")
            if source_info.prompt_references:
                sections.append(f"**Prompt References:** {', '.join(source_info.prompt_references)}\n")
            if source_info.state_fields_read:
                sections.append(f"**State Fields Read:** {', '.join(source_info.state_fields_read)}\n")
            
            # Include source code (truncated if too long)
            code = source_info.source_code
            if len(code) > 8000:
                code = code[:8000] + "\n\n[... truncated ...]"
            sections.append(f"\n**Full Source:**\n```python\n{code}\n```\n")
        
        # Metrics section
        sections.append("\n## Execution Metrics\n")
        sections.append(f"- **Executions Analyzed:** {metrics.get('total_executions', 0)}\n")
        sections.append(f"- **Success Rate:** {metrics.get('success_rate', 0):.1%}\n")
        sections.append(f"- **Avg Duration:** {metrics.get('avg_duration_ms', 0):.2f}ms\n")
        sections.append(f"- **Total LLM Calls:** {metrics.get('total_llm_calls', 0)}\n")
        sections.append(f"- **Avg LLM Calls/Exec:** {metrics.get('avg_llm_calls_per_exec', 0):.1f}\n")
        sections.append(f"- **Models Used:** {', '.join(metrics.get('models_used', []))}\n")
        sections.append(f"- **Temperatures:** {metrics.get('temperatures_used', [])}\n")
        sections.append(f"- **Total Cost:** ${metrics.get('total_cost', 0):.6f}\n")
        sections.append(f"- **Avg Cost/Exec:** ${metrics.get('avg_cost_per_exec', 0):.6f}\n")
        sections.append(f"- **Avg Prompt Length:** {metrics.get('avg_prompt_length', 0):.0f} chars\n")
        
        if metrics.get('common_errors'):
            sections.append(f"\n**Common Errors:**\n")
            for err in metrics['common_errors']:
                sections.append(f"- {err}\n")
        
        # Sample executions
        sections.append("\n## Sample Executions\n")
        sample_count = 0
        for run, execs in executions[:3]:  # Limit to 3 runs
            for exec in execs[:2]:  # Limit to 2 executions per run
                sample_count += 1
                sections.append(f"\n### Execution {sample_count} (Run {run.summary.run_id})\n")
                sections.append(f"**Timestamp:** {exec.timestamp}\n")
                sections.append(f"**Success:** {exec.success}\n")
                sections.append(f"**Duration:** {exec.duration_ms:.2f}ms\n")
                
                # State on entry (summarized)
                entry_summary = self._summarize_state(exec.state_on_entry)
                sections.append(f"\n**State on Entry (summary):**\n```json\n{entry_summary}\n```\n")
                
                # LLM calls
                for i, call in enumerate(exec.llm_calls[:2], 1):  # Limit calls shown
                    sections.append(f"\n**LLM Call {i}:**\n")
                    sections.append(f"- Model: {call.model}, Temp: {call.temperature}\n")
                    sections.append(f"- Tokens: {call.input_tokens} in / {call.output_tokens} out\n")
                    sections.append(f"- Cost: ${call.cost_estimate:.6f}\n")
                    
                    # Prompt (truncated)
                    prompt = call.prompt
                    if len(prompt) > 2000:
                        prompt = prompt[:2000] + "\n\n[... truncated ...]"
                    sections.append(f"\n**Prompt:**\n```\n{prompt}\n```\n")
                    
                    # Response (truncated)
                    response = call.response
                    if len(response) > 1000:
                        response = response[:1000] + "\n\n[... truncated ...]"
                    sections.append(f"\n**Response:**\n```\n{response}\n```\n")
                
                if exec.state_on_exit:
                    exit_summary = self._summarize_state(exec.state_on_exit)
                    sections.append(f"\n**State on Exit (summary):**\n```json\n{exit_summary}\n```\n")
        
        return "".join(sections)
    
    def _summarize_state(self, state: dict[str, Any], max_value_len: int = 200) -> str:
        """Create a summarized view of state."""
        import json
        
        def truncate(v: Any) -> Any:
            if isinstance(v, str) and len(v) > max_value_len:
                return v[:max_value_len] + "..."
            if isinstance(v, list) and len(v) > 5:
                return v[:5] + ["... and more"]
            if isinstance(v, dict):
                return {k: truncate(val) for k, val in list(v.items())[:10]}
            return v
        
        summarized = {k: truncate(v) for k, v in state.items()}
        try:
            return json.dumps(summarized, indent=2, default=str)
        except Exception:
            return str(summarized)
    
    def get_all_node_names(self) -> list[str]:
        """Get all node names from the nodes directory.
        
        Returns:
            List of node function names
        """
        names = []
        for f in self.nodes_dir.glob("*.py"):
            if f.name.startswith("_"):
                continue
            try:
                content = f.read_text()
                # Find function definitions that look like nodes
                for match in re.finditer(r'(?:async\s+)?def\s+(\w+_node)\s*\(', content):
                    names.append(match.group(1))
                # Also find any function with state parameter
                for match in re.finditer(r'(?:async\s+)?def\s+(\w+)\s*\(\s*state\s*:', content):
                    if match.group(1) not in names:
                        names.append(match.group(1))
            except Exception:
                continue
        return sorted(set(names))
