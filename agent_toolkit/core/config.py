"""Configuration for the Agent Toolkit.

This module provides configuration management for the toolkit, allowing
customization via environment variables, config files, or direct parameters.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    # Try to find .env in current directory or parent directories
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        # Try parent directories
        for parent in Path.cwd().parents:
            env_path = parent / ".env"
            if env_path.exists():
                load_dotenv(env_path)
                break
except ImportError:
    pass  # dotenv not installed, rely on system env vars


@dataclass
class ToolkitConfig:
    """Configuration for agent toolkit.
    
    Attributes:
        project_root: Root directory of the LangGraph project
        trace_dir: Directory where trace logs are stored
        nodes_dir: Directory containing node implementations
        prompts_dir: Directory containing prompt templates
        graph_module: Module path to the main graph
        readme_path: Path to project README
        analysis_model: Model to use for analysis LLM calls
        analysis_temperature: Temperature for analysis calls
        max_trace_age_days: Max age of traces to consider
        output_dir: Directory for analysis outputs
    """
    
    project_root: Path = field(default_factory=lambda: Path.cwd())
    trace_dir: str = "output/logs"
    nodes_dir: str = "src/nodes"
    prompts_dir: str = "src/prompts"
    graph_module: str = "src.graphs.main_graph"
    readme_path: str = "README.md"
    decisions_dir: str = "docs/decisions"  # Architecture Decision Records
    
    # LLM settings for analysis
    # NOTE: Use GPT-5.2 for all analysis - project standard (best for coding/agentic tasks)
    analysis_model: str = "gpt-5.2"
    analysis_temperature: float = 0.1
    
    # Analysis settings
    max_trace_age_days: int = 30
    output_dir: str = "output/analysis"
    
    # Cost tracking (per 1M tokens: input, output)
    model_costs: dict[str, tuple[float, float]] = field(default_factory=lambda: {
        "gpt-5.2": (1.75, 14.0),  # $1.75/1M input, $14/1M output
        "gpt-5.2-pro": (21.0, 168.0),
        "gpt-5-mini": (0.25, 2.0),
        "gpt-4.1": (2.0, 8.0),
        "gpt-4o": (0.0025, 0.01),
        "gpt-4o-mini": (0.00015, 0.0006),
        "gpt-4-turbo": (0.01, 0.03),
        "gpt-3.5-turbo": (0.0005, 0.0015),
        "claude-3-5-sonnet-20241022": (0.003, 0.015),
        "claude-3-opus-20240229": (0.015, 0.075),
    })
    
    @classmethod
    def from_env(cls) -> "ToolkitConfig":
        """Create config from environment variables."""
        return cls(
            project_root=Path(os.getenv("AGENT_PROJECT_ROOT", Path.cwd())),
            trace_dir=os.getenv("AGENT_TRACE_DIR", "output/logs"),
            nodes_dir=os.getenv("AGENT_NODES_DIR", "src/nodes"),
            prompts_dir=os.getenv("AGENT_PROMPTS_DIR", "src/prompts"),
            graph_module=os.getenv("AGENT_GRAPH_MODULE", "src.graphs.main_graph"),
            readme_path=os.getenv("AGENT_README_PATH", "README.md"),
            decisions_dir=os.getenv("AGENT_DECISIONS_DIR", "docs/decisions"),
            analysis_model=os.getenv("AGENT_ANALYSIS_MODEL", "gpt-5.2"),
            analysis_temperature=float(os.getenv("AGENT_ANALYSIS_TEMP", "0.1")),
            max_trace_age_days=int(os.getenv("AGENT_MAX_TRACE_AGE", "30")),
            output_dir=os.getenv("AGENT_OUTPUT_DIR", "output/analysis"),
        )
    
    @classmethod
    def from_file(cls, config_path: str | Path) -> "ToolkitConfig":
        """Load config from JSON file."""
        with open(config_path) as f:
            data = json.load(f)
        
        # Convert project_root to Path
        if "project_root" in data:
            data["project_root"] = Path(data["project_root"])
        
        return cls(**data)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "project_root": str(self.project_root),
            "trace_dir": self.trace_dir,
            "nodes_dir": self.nodes_dir,
            "prompts_dir": self.prompts_dir,
            "graph_module": self.graph_module,
            "readme_path": self.readme_path,
            "decisions_dir": self.decisions_dir,
            "analysis_model": self.analysis_model,
            "analysis_temperature": self.analysis_temperature,
            "max_trace_age_days": self.max_trace_age_days,
            "output_dir": self.output_dir,
        }
    
    def save(self, config_path: str | Path) -> None:
        """Save config to JSON file."""
        with open(config_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
    
    def get_trace_path(self) -> Path:
        """Get full path to trace directory."""
        return self.project_root / self.trace_dir
    
    def get_nodes_path(self) -> Path:
        """Get full path to nodes directory."""
        return self.project_root / self.nodes_dir
    
    def get_prompts_path(self) -> Path:
        """Get full path to prompts directory."""
        return self.project_root / self.prompts_dir
    
    def get_readme_path(self) -> Path:
        """Get full path to README."""
        return self.project_root / self.readme_path
    
    def get_decisions_path(self) -> Path:
        """Get full path to decisions/ADR directory."""
        return self.project_root / self.decisions_dir
    
    def get_output_path(self) -> Path:
        """Get full path to output directory."""
        path = self.project_root / self.output_dir
        path.mkdir(parents=True, exist_ok=True)
        return path


# Global config instance
_config: ToolkitConfig | None = None


def get_config() -> ToolkitConfig:
    """Get the global toolkit config."""
    global _config
    if _config is None:
        _config = ToolkitConfig.from_env()
    return _config


def set_config(config: ToolkitConfig) -> None:
    """Set the global toolkit config."""
    global _config
    _config = config
