#!/usr/bin/env python3
"""agent_health - Health check tool for LangGraph agents.

Performs comprehensive health diagnostics on your LangGraph agent project.

Checks:
- Project structure validation
- Configuration validation
- Trace availability
- Graph compilation
- Node coverage
- Common issues detection
"""

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Add parent to path for imports when run directly
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent_toolkit.core.config import ToolkitConfig, get_config, set_config


@dataclass
class HealthCheckResult:
    """Result of a single health check."""
    
    name: str
    passed: bool
    message: str
    severity: str = "info"  # info, warning, error, critical
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthReport:
    """Complete health report."""
    
    project_name: str
    checks: list[HealthCheckResult]
    
    @property
    def passed(self) -> bool:
        """Overall pass status (no critical or error checks failed)."""
        return not any(
            not c.passed and c.severity in ("error", "critical")
            for c in self.checks
        )
    
    @property
    def critical_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed and c.severity == "critical")
    
    @property
    def error_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed and c.severity == "error")
    
    @property
    def warning_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed and c.severity == "warning")
    
    def format_report(self) -> str:
        """Format report for display."""
        lines = [
            "=" * 60,
            "AGENT HEALTH CHECK REPORT",
            "=" * 60,
            f"Project: {self.project_name}",
            "",
        ]
        
        # Summary
        status = "✅ HEALTHY" if self.passed else "❌ ISSUES FOUND"
        lines.append(f"Status: {status}")
        
        if self.critical_count:
            lines.append(f"  🔴 Critical: {self.critical_count}")
        if self.error_count:
            lines.append(f"  🟠 Errors: {self.error_count}")
        if self.warning_count:
            lines.append(f"  🟡 Warnings: {self.warning_count}")
        
        lines.append("")
        lines.append("-" * 60)
        lines.append("")
        
        # Individual checks
        for check in self.checks:
            icon = "✅" if check.passed else {
                "critical": "🔴",
                "error": "🟠",
                "warning": "🟡",
                "info": "ℹ️",
            }.get(check.severity, "❓")
            
            lines.append(f"{icon} {check.name}")
            lines.append(f"   {check.message}")
            
            if check.details:
                for key, value in check.details.items():
                    lines.append(f"     • {key}: {value}")
            
            lines.append("")
        
        lines.append("=" * 60)
        return "\n".join(lines)


class HealthChecker:
    """Performs health checks on LangGraph projects."""
    
    def __init__(self, config: ToolkitConfig | None = None):
        self.config = config or get_config()
        self.checks: list[HealthCheckResult] = []
    
    def run_all_checks(self) -> HealthReport:
        """Run all health checks.
        
        Returns:
            HealthReport with all results
        """
        self.checks = []
        
        # Run checks in order
        self._check_project_structure()
        self._check_environment()
        self._check_graph_module()
        self._check_nodes_directory()
        self._check_prompts_directory()
        self._check_trace_directory()
        self._check_dependencies()
        self._check_configuration()
        
        return HealthReport(
            project_name=self.config.project_root.name,
            checks=self.checks,
        )
    
    def _check_project_structure(self):
        """Check basic project structure."""
        root = self.config.project_root
        
        # Check for essential files
        essential_files = [
            "pyproject.toml",
            "README.md",
        ]
        
        missing = []
        for f in essential_files:
            if not (root / f).exists():
                missing.append(f)
        
        if missing:
            self.checks.append(HealthCheckResult(
                name="Project Structure",
                passed=False,
                message=f"Missing essential files: {', '.join(missing)}",
                severity="warning",
                details={"missing_files": missing},
            ))
        else:
            self.checks.append(HealthCheckResult(
                name="Project Structure",
                passed=True,
                message="All essential files present",
            ))
        
        # Check for essential directories
        essential_dirs = [
            self.config.nodes_dir,
        ]
        
        missing_dirs = []
        for d in essential_dirs:
            if not (root / d).exists():
                missing_dirs.append(d)
        
        if missing_dirs:
            self.checks.append(HealthCheckResult(
                name="Directory Structure",
                passed=False,
                message=f"Missing directories: {', '.join(missing_dirs)}",
                severity="error",
                details={"missing_directories": missing_dirs},
            ))
        else:
            self.checks.append(HealthCheckResult(
                name="Directory Structure",
                passed=True,
                message="All essential directories present",
            ))
    
    def _check_environment(self):
        """Check environment variables."""
        required_vars = ["OPENAI_API_KEY"]
        optional_vars = ["LANGCHAIN_API_KEY", "LOCAL_TRACING"]
        
        missing_required = []
        for var in required_vars:
            if not os.getenv(var):
                missing_required.append(var)
        
        if missing_required:
            self.checks.append(HealthCheckResult(
                name="Environment Variables",
                passed=False,
                message=f"Missing required variables: {', '.join(missing_required)}",
                severity="critical",
                details={"missing": missing_required},
            ))
        else:
            present_optional = [v for v in optional_vars if os.getenv(v)]
            self.checks.append(HealthCheckResult(
                name="Environment Variables",
                passed=True,
                message="All required variables set",
                details={"optional_present": present_optional} if present_optional else {},
            ))
    
    def _check_graph_module(self):
        """Check if graph module can be imported."""
        try:
            import importlib
            module = importlib.import_module(self.config.graph_module)
            
            # Look for graph object
            graph = None
            for name in ["graph", "pd_graph", "app", "workflow", "agent", "build_graph"]:
                if hasattr(module, name):
                    obj = getattr(module, name)
                    if callable(obj) and name == "build_graph":
                        graph = obj()
                    else:
                        graph = obj
                    break
            
            if graph:
                self.checks.append(HealthCheckResult(
                    name="Graph Module",
                    passed=True,
                    message=f"Graph module loads correctly",
                    details={"module": self.config.graph_module},
                ))
            else:
                self.checks.append(HealthCheckResult(
                    name="Graph Module",
                    passed=False,
                    message="Graph module found but no graph object detected",
                    severity="error",
                ))
                
        except ImportError as e:
            self.checks.append(HealthCheckResult(
                name="Graph Module",
                passed=False,
                message=f"Cannot import graph module: {e}",
                severity="error",
            ))
        except Exception as e:
            self.checks.append(HealthCheckResult(
                name="Graph Module",
                passed=False,
                message=f"Error loading graph: {e}",
                severity="error",
            ))
    
    def _check_nodes_directory(self):
        """Check nodes directory."""
        nodes_path = self.config.get_nodes_path()
        
        if not nodes_path.exists():
            self.checks.append(HealthCheckResult(
                name="Nodes Directory",
                passed=False,
                message=f"Nodes directory not found: {nodes_path}",
                severity="error",
            ))
            return
        
        # Count node files
        node_files = list(nodes_path.glob("*_node.py"))
        all_py_files = list(nodes_path.glob("*.py"))
        
        if not node_files and not all_py_files:
            self.checks.append(HealthCheckResult(
                name="Nodes Directory",
                passed=False,
                message="No Python files found in nodes directory",
                severity="error",
            ))
        else:
            self.checks.append(HealthCheckResult(
                name="Nodes Directory",
                passed=True,
                message=f"Found {len(all_py_files)} Python files, {len(node_files)} node files",
                details={
                    "total_files": len(all_py_files),
                    "node_files": len(node_files),
                },
            ))
    
    def _check_prompts_directory(self):
        """Check prompts directory."""
        prompts_path = self.config.get_prompts_path()
        
        if not prompts_path.exists():
            self.checks.append(HealthCheckResult(
                name="Prompts Directory",
                passed=True,
                message="No prompts directory (this may be fine if using inline prompts)",
                severity="info",
            ))
            return
        
        # Count prompt files
        prompt_files = list(prompts_path.glob("*.py")) + list(prompts_path.glob("*.j2")) + list(prompts_path.glob("*.jinja2"))
        
        self.checks.append(HealthCheckResult(
            name="Prompts Directory",
            passed=True,
            message=f"Found {len(prompt_files)} prompt files",
            details={"prompt_files": len(prompt_files)},
        ))
    
    def _check_trace_directory(self):
        """Check trace/logs directory."""
        trace_path = self.config.get_trace_path()
        
        if not trace_path.exists():
            self.checks.append(HealthCheckResult(
                name="Trace Directory",
                passed=True,
                message="Trace directory not created yet (will be created when tracing is enabled)",
                severity="info",
            ))
            return
        
        # Count trace files
        trace_files = list(trace_path.glob("*.jsonl"))
        
        if not trace_files:
            self.checks.append(HealthCheckResult(
                name="Trace Directory",
                passed=True,
                message="Trace directory exists but no traces yet",
                severity="info",
                details={"hint": "Run agent with LOCAL_TRACING=true to generate traces"},
            ))
        else:
            # Get most recent trace info
            newest = max(trace_files, key=lambda f: f.stat().st_mtime)
            from datetime import datetime
            newest_time = datetime.fromtimestamp(newest.stat().st_mtime)
            
            self.checks.append(HealthCheckResult(
                name="Trace Directory",
                passed=True,
                message=f"Found {len(trace_files)} trace files",
                details={
                    "trace_count": len(trace_files),
                    "newest": newest.name,
                    "newest_time": newest_time.strftime("%Y-%m-%d %H:%M"),
                },
            ))
    
    def _check_dependencies(self):
        """Check key dependencies."""
        required = ["langgraph", "langchain_openai", "pydantic"]
        missing = []
        
        for dep in required:
            try:
                __import__(dep)
            except ImportError:
                missing.append(dep)
        
        if missing:
            self.checks.append(HealthCheckResult(
                name="Dependencies",
                passed=False,
                message=f"Missing dependencies: {', '.join(missing)}",
                severity="critical",
                details={"missing": missing},
            ))
        else:
            # Get versions
            versions = {}
            for dep in required:
                try:
                    mod = __import__(dep)
                    versions[dep] = getattr(mod, "__version__", "unknown")
                except Exception:
                    pass
            
            self.checks.append(HealthCheckResult(
                name="Dependencies",
                passed=True,
                message="All required dependencies installed",
                details={"versions": versions},
            ))
    
    def _check_configuration(self):
        """Check configuration validity."""
        issues = []
        
        # Check model costs are defined
        if not self.config.model_costs:
            issues.append("No model costs defined")
        
        # Check paths are reasonable
        if not str(self.config.nodes_dir).strip():
            issues.append("Nodes directory not configured")
        
        if issues:
            self.checks.append(HealthCheckResult(
                name="Configuration",
                passed=False,
                message=f"Configuration issues: {', '.join(issues)}",
                severity="warning",
            ))
        else:
            self.checks.append(HealthCheckResult(
                name="Configuration",
                passed=True,
                message="Configuration looks valid",
            ))


def run_health_check(config: ToolkitConfig | None = None) -> HealthReport:
    """Run health check (sync wrapper).
    
    Args:
        config: Optional toolkit configuration
        
    Returns:
        HealthReport with all check results
    """
    checker = HealthChecker(config)
    return checker.run_all_checks()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="agent_health - Health check tool for LangGraph agents",
    )
    
    parser.add_argument(
        "--config",
        help="Path to config file",
    )
    parser.add_argument(
        "--project-root",
        help="Project root directory",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
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
    
    # Run health check
    report = run_health_check(config)
    
    if args.json:
        import json
        data = {
            "project": report.project_name,
            "passed": report.passed,
            "critical": report.critical_count,
            "errors": report.error_count,
            "warnings": report.warning_count,
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "severity": c.severity,
                    "message": c.message,
                    "details": c.details,
                }
                for c in report.checks
            ],
        }
        print(json.dumps(data, indent=2))
    else:
        print(report.format_report())
    
    sys.exit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
